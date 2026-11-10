"""Authorization regression tests for Phase 3B-3.

These tests run against an isolated in-memory SQLite database. They never touch
the live MySQL data, and they never print passwords, cookies or CSRF tokens.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (register all tables in metadata)
from app.core.config import get_settings
from app.core.security import utcnow
from app.database import Base, get_db
from app.main import app
from app.models.auth_session import AuthSession
from app.models.enums import UserRole
from app.models.incident import Incident
from app.models.status_history import StatusHistory
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


class AuthorizationAPITests(unittest.TestCase):
    password = "CorrectHorseBattery9"

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

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def create_user(
        self,
        *,
        email: str = "dispatcher@example.org",
        role: UserRole | str = UserRole.dispatcher,
        is_active: bool = True,
    ) -> int:
        with TestingSessionLocal() as db:
            user = auth_service.create_user(
                db,
                email=email,
                password=self.password,
                role=role,
                is_active=is_active,
            )
            return user.id

    def login(self, email: str = "dispatcher@example.org"):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return response

    @staticmethod
    def csrf_token(login_response) -> str:
        return login_response.cookies[settings.csrf_cookie_name]

    @staticmethod
    def csrf_headers(csrf_token: str) -> dict[str, str]:
        return {settings.csrf_header_name: csrf_token}

    def seed_incident(
        self,
        *,
        tracking_id: str = "CP-20261108-SEED01",
        status: str = "Submitted",
    ) -> int:
        with TestingSessionLocal() as db:
            incident = Incident(
                tracking_id=tracking_id,
                category="pothole",
                description="Original incident description.",
                severity="low",
                priority="low",
                status=status,
                latitude=23.0225,
                longitude=72.5714,
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)
            return incident.id

    def seed_status_history(self, incident_id: int) -> int:
        with TestingSessionLocal() as db:
            history = StatusHistory(
                incident_id=incident_id,
                old_status=None,
                new_status="Submitted",
                notes="Pre-existing audit row.",
            )
            db.add(history)
            db.commit()
            db.refresh(history)
            return history.id

    # ------------------------------------------------------------------
    # Anonymous / session behaviour
    # ------------------------------------------------------------------
    def test_anonymous_access_to_protected_endpoints_is_401(self) -> None:
        incident_id = self.seed_incident()

        cases = (
            ("get", "/api/v1/incidents", None),
            ("get", f"/api/v1/incidents/{incident_id}", None),
            ("patch", f"/api/v1/incidents/{incident_id}", {"status": "In Progress"}),
            ("get", "/api/v1/admin/overview", None),
            ("get", "/api/v1/reports/summary", None),
        )

        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                kwargs = {"json": body} if body is not None else {}
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)

    def test_invalid_session_cookie_is_rejected(self) -> None:
        response = self.client.get(
            "/api/v1/incidents",
            headers={
                "Cookie": f"{settings.auth_cookie_name}=not-a-valid-session-token"
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_expired_session_is_rejected_on_protected_route(self) -> None:
        self.create_user()
        self.login()

        with TestingSessionLocal() as db:
            stored = db.scalar(select(AuthSession))
            stored.expires_at = utcnow() - timedelta(seconds=1)
            db.add(stored)
            db.commit()

        response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 401)

    def test_revoked_session_is_rejected_on_protected_route(self) -> None:
        self.create_user()
        login_response = self.login()
        session_token = login_response.cookies[settings.auth_cookie_name]
        csrf_token = self.csrf_token(login_response)

        logout_response = self.client.post(
            "/api/v1/auth/logout",
            headers=self.csrf_headers(csrf_token),
        )
        self.assertEqual(logout_response.status_code, 204)

        replay_client = TestClient(app)
        replay = replay_client.get(
            "/api/v1/incidents",
            headers={
                "Cookie": f"{settings.auth_cookie_name}={session_token}",
            },
        )
        self.assertEqual(replay.status_code, 401)

    def test_inactive_user_session_is_rejected_on_protected_route(self) -> None:
        user_id = self.create_user()
        self.login()

        with TestingSessionLocal() as db:
            user = db.get(User, user_id)
            user.is_active = False
            db.add(user)
            db.commit()

        response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # Role matrix
    # ------------------------------------------------------------------
    def test_dispatcher_can_access_permitted_routes_but_not_admin_overview(
        self,
    ) -> None:
        incident_id = self.seed_incident()
        self.create_user(role=UserRole.dispatcher)
        login_response = self.login()
        csrf_token = self.csrf_token(login_response)

        self.assertEqual(self.client.get("/api/v1/incidents").status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/v1/incidents", params={"status": "Submitted"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/incidents", params={"status": "NotARealStatus"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(f"/api/v1/incidents/{incident_id}").status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/v1/reports/summary").status_code,
            200,
        )

        updated = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
            headers=self.csrf_headers(csrf_token),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "In Progress")

        self.assertEqual(
            self.client.get("/api/v1/admin/overview").status_code,
            403,
        )

    def test_viewer_cannot_access_staff_routes_or_update_incidents(self) -> None:
        incident_id = self.seed_incident()
        self.create_user(
            email="viewer@example.org",
            role=UserRole.viewer,
        )
        login_response = self.login("viewer@example.org")
        csrf_token = self.csrf_token(login_response)

        for path in (
            "/api/v1/incidents",
            f"/api/v1/incidents/{incident_id}",
            "/api/v1/reports/summary",
            "/api/v1/admin/overview",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        incident_update = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
            headers=self.csrf_headers(csrf_token),
        )
        self.assertEqual(incident_update.status_code, 403)

    def test_admin_can_access_admin_and_staff_routes(self) -> None:
        incident_id = self.seed_incident()
        self.create_user(email="admin@example.org", role=UserRole.admin)
        login_response = self.login("admin@example.org")
        csrf_token = self.csrf_token(login_response)

        self.assertEqual(self.client.get("/api/v1/admin/overview").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/incidents").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/incidents/{incident_id}").status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/v1/reports/summary").status_code,
            200,
        )

        updated = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "Resolved"},
            headers=self.csrf_headers(csrf_token),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "Resolved")

    # ------------------------------------------------------------------
    # CSRF
    # ------------------------------------------------------------------
    def test_incident_update_requires_valid_csrf(self) -> None:
        incident_id = self.seed_incident()
        self.create_user()
        login_response = self.login()
        csrf_token = self.csrf_token(login_response)

        missing = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
        )
        self.assertEqual(missing.status_code, 403)

        wrong = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
            headers={settings.csrf_header_name: "wrong-token"},
        )
        self.assertEqual(wrong.status_code, 403)

        with TestingSessionLocal() as db:
            incident = db.get(Incident, incident_id)
            self.assertEqual(incident.status, "Submitted")
            self.assertEqual(db.scalar(select(StatusHistory)), None)

        valid = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
            headers=self.csrf_headers(csrf_token),
        )
        self.assertEqual(valid.status_code, 200)

    # ------------------------------------------------------------------
    # Status workflow / audit
    # ------------------------------------------------------------------
    def test_invalid_incident_status_and_unknown_fields_are_rejected(self) -> None:
        incident_id = self.seed_incident()
        self.create_user()
        login_response = self.login()
        csrf_token = self.csrf_token(login_response)
        headers = self.csrf_headers(csrf_token)

        for invalid_status in ("Hacked", "submitted", "Open", "Investigating", ""):
            with self.subTest(status=invalid_status):
                response = self.client.patch(
                    f"/api/v1/incidents/{incident_id}",
                    json={"status": invalid_status},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 422)

        null_status = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": None},
            headers=headers,
        )
        self.assertEqual(null_status.status_code, 422)

        for forbidden_field in (
            {"assigned_to_user_id": 1},
            {"tracking_id": "CP-20261108-REWRITE"},
            {"id": 999},
            {"created_at": "2026-01-01T00:00:00"},
        ):
            with self.subTest(payload=forbidden_field):
                response = self.client.patch(
                    f"/api/v1/incidents/{incident_id}",
                    json=forbidden_field,
                    headers=headers,
                )
                self.assertEqual(response.status_code, 422)

        with TestingSessionLocal() as db:
            incident = db.get(Incident, incident_id)
            self.assertEqual(incident.status, "Submitted")
            self.assertEqual(incident.tracking_id, "CP-20261108-SEED01")

    def test_status_update_preserves_incident_and_appends_actor_history(self) -> None:
        incident_id = self.seed_incident()
        existing_history_id = self.seed_status_history(incident_id)
        user_id = self.create_user()
        login_response = self.login()
        csrf_token = self.csrf_token(login_response)

        response = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
            headers=self.csrf_headers(csrf_token),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "In Progress")
        self.assertEqual(payload["category"], "pothole")
        self.assertEqual(payload["description"], "Original incident description.")
        self.assertEqual(payload["tracking_id"], "CP-20261108-SEED01")

        with TestingSessionLocal() as db:
            incident = db.get(Incident, incident_id)
            self.assertIsNotNone(incident)
            self.assertEqual(incident.status, "In Progress")
            self.assertEqual(incident.category, "pothole")
            self.assertEqual(incident.description, "Original incident description.")
            self.assertEqual(incident.severity, "low")
            self.assertEqual(incident.priority, "low")
            self.assertEqual(incident.tracking_id, "CP-20261108-SEED01")
            self.assertEqual(
                db.scalar(select(func.count()).select_from(Incident)),
                1,
            )

            history_rows = list(
                db.scalars(
                    select(StatusHistory)
                    .where(StatusHistory.incident_id == incident_id)
                    .order_by(StatusHistory.id)
                ).all()
            )
            self.assertEqual(len(history_rows), 2)
            self.assertEqual(history_rows[0].id, existing_history_id)
            self.assertEqual(history_rows[0].notes, "Pre-existing audit row.")
            self.assertIsNone(history_rows[0].changed_by_user_id)
            self.assertEqual(history_rows[1].old_status, "Submitted")
            self.assertEqual(history_rows[1].new_status, "In Progress")
            self.assertEqual(history_rows[1].changed_by_user_id, user_id)
            self.assertIn("authenticated", history_rows[1].notes)

    # ------------------------------------------------------------------
    # Public workflow
    # ------------------------------------------------------------------
    def test_public_incident_submission_and_tracking_remain_public(self) -> None:
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
        self.assertEqual(created.json()["status"], "Submitted")

        tracked = self.client.get(f"/api/v1/tracking/{tracking_id}")
        self.assertEqual(tracked.status_code, 200)
        payload = tracked.json()
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
        self.assertEqual(payload["tracking_id"], tracking_id)
        self.assertNotIn("description", payload)

        non_submitted = self.client.post(
            "/api/v1/incidents",
            json={"category": "pothole", "status": "Resolved"},
        )
        self.assertEqual(non_submitted.status_code, 422)

        unexpected_field = self.client.post(
            "/api/v1/incidents",
            json={"category": "pothole", "assigned_to_user_id": 7},
        )
        self.assertEqual(unexpected_field.status_code, 422)


if __name__ == "__main__":
    unittest.main()
