"""Security regression tests for Phase 3B-2 authentication.

The tests use an isolated in-memory SQLite database and override FastAPI's
``get_db`` dependency, so the live MySQL data is never touched.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import cli as cli_module
from app import models  # noqa: F401  (register all tables in metadata)
from app.core.config import get_settings
from app.core.dependencies import get_current_user, require_roles
from app.core.security import hash_password, utcnow, verify_password
from app.database import Base, get_db
from app.main import app
from app.models.auth_session import AuthSession
from app.models.enums import UserRole
from app.models.user import User
from app.services import auth as auth_service

settings = get_settings()

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=TEST_ENGINE,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class AuthAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_db, None)
        TEST_ENGINE.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        self.client = TestClient(app)

    def create_user(
        self,
        *,
        email: str = "dispatcher@example.org",
        password: str = "CorrectHorseBattery9",
        role: UserRole | str = UserRole.dispatcher,
        is_active: bool = True,
    ) -> int:
        with TestingSessionLocal() as db:
            user = auth_service.create_user(
                db,
                email=email,
                password=password,
                role=role,
                is_active=is_active,
            )
            return user.id

    def login(self, email: str, password: str):
        return self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )

    # ------------------------------------------------------------------
    # Login / password handling
    # ------------------------------------------------------------------
    def test_valid_login_returns_user_and_secure_cookies(self) -> None:
        self.create_user(email="Admin.User@Example.org")

        response = self.login("  admin.user@example.org ", "CorrectHorseBattery9")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["email"], "admin.user@example.org")
        self.assertEqual(payload["user"]["role"], "dispatcher")
        self.assertNotIn("password", payload["user"])
        self.assertNotIn("password_hash", payload["user"])

        cookies = response.headers.get_list("set-cookie")
        session_cookie = next(
            value for value in cookies if value.startswith(settings.auth_cookie_name + "=")
        )
        csrf_cookie = next(
            value for value in cookies if value.startswith(settings.csrf_cookie_name + "=")
        )
        self.assertIn("HttpOnly", session_cookie)
        self.assertNotIn("HttpOnly", csrf_cookie)
        self.assertIn("SameSite=lax", session_cookie)
        self.assertIn("Path=/", session_cookie)

        me_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["email"], "admin.user@example.org")

        with TestingSessionLocal() as db:
            stored = db.scalar(select(AuthSession))
            self.assertIsNotNone(stored)
            self.assertEqual(len(stored.token_hash), 64)
            self.assertNotEqual(
                stored.token_hash, response.cookies[settings.auth_cookie_name]
            )
            user = db.get(User, payload["user"]["id"])
            self.assertIsNotNone(user.last_login_at)

    def test_invalid_credentials_are_generic_and_do_not_create_session(self) -> None:
        self.create_user()

        wrong_password = self.login("dispatcher@example.org", "wrong-password")
        unknown_email = self.login("nobody@example.org", "wrong-password")

        for response in (wrong_password, unknown_email):
            self.assertEqual(response.status_code, 401)
            self.assertEqual(
                response.json()["detail"], auth_service.GENERIC_AUTH_ERROR
            )
            self.assertNotIn(settings.auth_cookie_name, response.cookies)

        with TestingSessionLocal() as db:
            self.assertEqual(db.scalar(select(AuthSession)), None)
            user = db.scalar(select(User))
            self.assertEqual(user.failed_login_count, 1)

    def test_inactive_account_cannot_log_in(self) -> None:
        self.create_user(is_active=False)

        response = self.login("dispatcher@example.org", "CorrectHorseBattery9")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], auth_service.GENERIC_AUTH_ERROR)
        self.assertNotIn(settings.auth_cookie_name, response.cookies)

    def test_password_hashes_are_argon2id_and_plaintext_is_absent(self) -> None:
        self.create_user(password="PlaintextNeverStored9")

        with TestingSessionLocal() as db:
            user = db.scalar(select(User))
            self.assertTrue(user.password_hash.startswith("$argon2id$"))
            self.assertNotEqual(user.password_hash, "PlaintextNeverStored9")
            self.assertNotIn("PlaintextNeverStored9", user.password_hash)
            self.assertTrue(verify_password(user.password_hash, "PlaintextNeverStored9"))
            self.assertFalse(verify_password(user.password_hash, "WrongPassword9"))

        first = hash_password("SamePasswordTwice9")
        second = hash_password("SamePasswordTwice9")
        self.assertNotEqual(first, second)

    def test_brute_force_lockout_blocks_correct_password(self) -> None:
        self.create_user()
        for _ in range(settings.login_max_failures):
            response = self.login("dispatcher@example.org", "wrong-password")
            self.assertEqual(response.status_code, 401)

        locked_response = self.login(
            "dispatcher@example.org", "CorrectHorseBattery9"
        )

        self.assertEqual(locked_response.status_code, 401)
        with TestingSessionLocal() as db:
            user = db.scalar(select(User))
            self.assertIsNotNone(user.locked_until)
            self.assertGreater(user.locked_until, utcnow())

    # ------------------------------------------------------------------
    # Protected operations / roles / CSRF / sessions
    # ------------------------------------------------------------------
    def test_anonymous_users_cannot_access_protected_operations(self) -> None:
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 401)

    def test_role_dependency_enforces_admin_only_access(self) -> None:
        admin_only = require_roles(UserRole.admin)

        viewer = SimpleNamespace(role=UserRole.viewer.value)
        with self.assertRaises(HTTPException) as raised:
            admin_only(viewer)
        self.assertEqual(raised.exception.status_code, 403)

        admin = SimpleNamespace(role=UserRole.admin.value)
        self.assertIs(admin_only(admin), admin)

        role_app = FastAPI()

        @role_app.get("/admin-only")
        def admin_route(user: User = Depends(require_roles(UserRole.admin))):
            return {"role": user.role}

        role_client = TestClient(role_app)
        role_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            role="viewer"
        )
        self.assertEqual(role_client.get("/admin-only").status_code, 403)

        role_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            role="admin"
        )
        self.assertEqual(role_client.get("/admin-only").status_code, 200)

    def test_logout_requires_csrf_and_invalidates_session(self) -> None:
        self.create_user()
        login_response = self.login(
            "dispatcher@example.org", "CorrectHorseBattery9"
        )
        session_token = login_response.cookies[settings.auth_cookie_name]
        csrf_token = login_response.cookies[settings.csrf_cookie_name]

        missing = self.client.post("/api/v1/auth/logout")
        self.assertEqual(missing.status_code, 403)

        wrong = self.client.post(
            "/api/v1/auth/logout", headers={settings.csrf_header_name: "wrong"}
        )
        self.assertEqual(wrong.status_code, 403)

        ok = self.client.post(
            "/api/v1/auth/logout",
            headers={settings.csrf_header_name: csrf_token},
        )
        self.assertEqual(ok.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)

        with TestingSessionLocal() as db:
            stored = db.scalar(select(AuthSession))
            self.assertIsNotNone(stored.revoked_at)

        replay_client = TestClient(app)
        replay = replay_client.get(
            "/api/v1/auth/me",
            headers={"Cookie": f"{settings.auth_cookie_name}={session_token}"},
        )
        self.assertEqual(replay.status_code, 401)

    def test_expired_session_is_rejected(self) -> None:
        self.create_user()
        login_response = self.login(
            "dispatcher@example.org", "CorrectHorseBattery9"
        )
        self.assertEqual(login_response.status_code, 200)

        with TestingSessionLocal() as db:
            stored = db.scalar(select(AuthSession))
            stored.expires_at = utcnow() - timedelta(seconds=1)
            db.add(stored)
            db.commit()

        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_deactivating_user_invalidates_existing_session(self) -> None:
        user_id = self.create_user()
        login_response = self.login(
            "dispatcher@example.org", "CorrectHorseBattery9"
        )
        self.assertEqual(login_response.status_code, 200)

        with TestingSessionLocal() as db:
            user = db.get(User, user_id)
            user.is_active = False
            db.add(user)
            db.commit()

        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)
        with TestingSessionLocal() as db:
            stored = db.scalar(select(AuthSession))
            self.assertIsNotNone(stored.revoked_at)

    # ------------------------------------------------------------------
    # One-time CLI bootstrap
    # ------------------------------------------------------------------
    def test_cli_bootstrap_creates_first_admin_without_default_password(self) -> None:
        password = "InteractiveAdminPass9"
        with (
            patch.object(cli_module, "SessionLocal", TestingSessionLocal),
            patch.object(
                cli_module.getpass,
                "getpass",
                side_effect=[password, password],
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            result = cli_module.create_admin("first.admin@example.org")

        self.assertEqual(result, 0)
        with TestingSessionLocal() as db:
            user = db.scalar(select(User))
            self.assertEqual(user.email, "first.admin@example.org")
            self.assertEqual(user.role, UserRole.admin.value)
            self.assertTrue(verify_password(user.password_hash, password))

    def test_cli_bootstrap_refuses_when_admin_already_exists(self) -> None:
        with TestingSessionLocal() as db:
            auth_service.create_user(
                db,
                email="existing.admin@example.org",
                password="ExistingAdminPass9",
                role=UserRole.admin,
            )

        with (
            patch.object(cli_module, "SessionLocal", TestingSessionLocal),
            patch.object(
                cli_module.getpass,
                "getpass",
                side_effect=["ShouldNotBeUsed9", "ShouldNotBeUsed9"],
            ) as prompt,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            result = cli_module.create_admin("second.admin@example.org")

        self.assertEqual(result, 1)
        prompt.assert_not_called()
        with TestingSessionLocal() as db:
            emails = set(db.scalars(select(User.email)).all())
        self.assertEqual(emails, {"existing.admin@example.org"})

    def test_cli_update_admin_changes_email_and_password_without_duplicate(self) -> None:
        old_password = "OldAdminPassword9"
        new_password = "NewAdminPassword9"
        admin_id = self.create_user(
            email="Demo.Admin@Example.org",
            password=old_password,
            role=UserRole.admin,
        )

        with TestingSessionLocal() as db:
            admin = db.get(User, admin_id)
            admin.failed_login_count = 4
            admin.locked_until = utcnow() + timedelta(minutes=5)
            db.add(admin)
            db.commit()

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(cli_module, "SessionLocal", TestingSessionLocal),
            patch.object(
                cli_module.getpass,
                "getpass",
                side_effect=[new_password, new_password],
            ) as prompt,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = cli_module.update_admin(
                " demo.admin@example.org ",
                "New.Admin@Example.org",
            )

        self.assertEqual(result, 0)
        self.assertEqual(prompt.call_count, 2)
        output = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(old_password, output)
        self.assertNotIn(new_password, output)

        with TestingSessionLocal() as db:
            users = db.scalars(select(User)).all()
            self.assertEqual(len(users), 1)
            admin = users[0]
            self.assertEqual(admin.email, "new.admin@example.org")
            self.assertEqual(admin.role, UserRole.admin.value)
            self.assertTrue(admin.is_active)
            self.assertTrue(verify_password(admin.password_hash, new_password))
            self.assertFalse(verify_password(admin.password_hash, old_password))
            self.assertEqual(admin.failed_login_count, 0)
            self.assertIsNone(admin.locked_until)

    def test_cli_update_admin_rejects_non_admin_target(self) -> None:
        old_password = "DispatcherPassword9"
        self.create_user(
            email="dispatcher@example.org",
            password=old_password,
            role=UserRole.dispatcher,
        )

        stderr = io.StringIO()
        with (
            patch.object(cli_module, "SessionLocal", TestingSessionLocal),
            patch.object(
                cli_module.getpass,
                "getpass",
                side_effect=["NewAdminPassword9", "NewAdminPassword9"],
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(stderr),
        ):
            result = cli_module.update_admin(
                "dispatcher@example.org",
                "new.admin@example.org",
            )

        self.assertEqual(result, 1)
        self.assertIn("Administrator account not found.", stderr.getvalue())
        with TestingSessionLocal() as db:
            users = db.scalars(select(User)).all()
            self.assertEqual(len(users), 1)
            dispatcher = users[0]
            self.assertEqual(dispatcher.email, "dispatcher@example.org")
            self.assertTrue(verify_password(dispatcher.password_hash, old_password))

    def test_cli_update_admin_rejects_duplicate_email(self) -> None:
        old_password = "OldAdminPassword9"
        self.create_user(
            email="admin@example.org",
            password=old_password,
            role=UserRole.admin,
        )
        self.create_user(
            email="taken@example.org",
            password="OtherUserPassword9",
            role=UserRole.viewer,
        )

        stderr = io.StringIO()
        with (
            patch.object(cli_module, "SessionLocal", TestingSessionLocal),
            patch.object(
                cli_module.getpass,
                "getpass",
                side_effect=["NewAdminPassword9", "NewAdminPassword9"],
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(stderr),
        ):
            result = cli_module.update_admin(
                "admin@example.org",
                "Taken@Example.org",
            )

        self.assertEqual(result, 1)
        self.assertIn("already exists", stderr.getvalue())
        with TestingSessionLocal() as db:
            admin = db.scalar(select(User).where(User.email == "admin@example.org"))
            self.assertIsNotNone(admin)
            self.assertTrue(verify_password(admin.password_hash, old_password))
            emails = set(db.scalars(select(User.email)).all())
        self.assertEqual(emails, {"admin@example.org", "taken@example.org"})

    def test_cli_update_admin_revokes_existing_sessions(self) -> None:
        old_password = "OldAdminPassword9"
        new_password = "NewAdminPassword9"
        self.create_user(
            email="admin@example.org",
            password=old_password,
            role=UserRole.admin,
        )
        login_response = self.login("admin@example.org", old_password)
        self.assertEqual(login_response.status_code, 200)

        with TestingSessionLocal() as db:
            session = db.scalar(select(AuthSession))
            self.assertIsNotNone(session)
            self.assertIsNone(session.revoked_at)

        with (
            patch.object(cli_module, "SessionLocal", TestingSessionLocal),
            patch.object(
                cli_module.getpass,
                "getpass",
                side_effect=[new_password, new_password],
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            result = cli_module.update_admin(
                "admin@example.org",
                "new.admin@example.org",
            )

        self.assertEqual(result, 0)
        with TestingSessionLocal() as db:
            session = db.scalar(select(AuthSession))
            self.assertIsNotNone(session)
            self.assertIsNotNone(session.revoked_at)

    # ------------------------------------------------------------------
    # Citizen access must remain public
    # ------------------------------------------------------------------
    def test_public_incident_reporting_and_tracking_still_work(self) -> None:
        created = self.client.post(
            "/api/v1/incidents",
            json={
                "category": "pothole",
                "description": "Large pothole near the school gate.",
                "severity": "high",
                "priority": "high",
            },
        )
        self.assertEqual(created.status_code, 201)
        tracking_id = created.json()["tracking_id"]

        tracked = self.client.get(f"/api/v1/tracking/{tracking_id}")
        self.assertEqual(tracked.status_code, 200)
        payload = tracked.json()
        self.assertEqual(payload["tracking_id"], tracking_id)
        self.assertEqual(payload["category"], "pothole")
        self.assertEqual(
            set(payload),
            {
                "tracking_id",
                "category",
                "status",
                "severity",
                "priority",
                "latitude",
                "longitude",
                "created_at",
            },
        )
        self.assertNotIn("description", payload)

    def test_openapi_security_matches_protected_endpoint_matrix(self) -> None:
        spec = self.client.get("/openapi.json").json()

        self.assertIn("SessionCookie", spec["components"]["securitySchemes"])

        protected = (
            ("/api/v1/auth/me", "get"),
            ("/api/v1/auth/logout", "post"),
            ("/api/v1/incidents", "get"),
            ("/api/v1/incidents/{incident_id}", "get"),
            ("/api/v1/incidents/{incident_id}", "patch"),
            ("/api/v1/reports/summary", "get"),
            ("/api/v1/admin/overview", "get"),
        )
        for path, method in protected:
            with self.subTest(path=path, method=method):
                self.assertEqual(
                    spec["paths"][path][method]["security"],
                    [{"SessionCookie": []}],
                )

        public = (
            ("/api/v1/auth/login", "post"),
            ("/api/v1/incidents", "post"),
            ("/api/v1/tracking/{tracking_id}", "get"),
        )
        for path, method in public:
            with self.subTest(path=path, method=method):
                self.assertNotIn("security", spec["paths"][path][method])

        for path, method in (
            ("/api/v1/auth/logout", "post"),
            ("/api/v1/incidents/{incident_id}", "patch"),
        ):
            with self.subTest(csrf_path=path):
                parameters = spec["paths"][path][method].get("parameters", [])
                self.assertIn(
                    settings.csrf_header_name,
                    [parameter["name"] for parameter in parameters],
                )


if __name__ == "__main__":
    unittest.main()
