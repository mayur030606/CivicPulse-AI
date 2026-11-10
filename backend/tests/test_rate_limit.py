"""Deterministic tests for Phase 3C-2C-1 rate limiting.

The tests use an isolated in-memory SQLite database and a fake clock. They do
not require Redis, do not call external providers, and never touch live MySQL.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import models  # noqa: F401  (register all tables in metadata)
from app.core.config import Settings, get_settings
from app.core.network import resolve_client_ip
from app.core.rate_limit import (
    AI_ANALYZE_IMAGE_POLICY,
    AI_UNDERSTAND_POLICY,
    INCIDENTS_CREATE_POLICY,
    LOGIN_POLICY,
    TRACKING_LOOKUP_POLICY,
    VOICE_SPEAK_POLICY,
    VOICE_TRANSCRIBE_POLICY,
    InMemoryRateLimitBackend,
    RateLimitBackendError,
    RateLimitPolicy,
    RateLimiter,
    build_policies,
    build_rate_limiter,
    get_rate_limiter,
    reset_rate_limiter,
)
from app.database import Base, get_db
from app.main import app
from app.models.enums import UserRole
from app.models.incident import Incident
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


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FailingRateLimitBackend:
    def check(self, key: str, limit: int, window_seconds: int, now: float):
        raise RateLimitBackendError("simulated backend failure")

    def close(self) -> None:
        return None


def make_settings(**overrides) -> Settings:
    values = {
        "environment": "development",
        "rate_limit_enabled": True,
        "rate_limit_backend": "memory",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_policies(
    *,
    incidents: int = 2,
    tracking: int = 3,
    login: int = 2,
    voice: int = 2,
    ai: int = 2,
) -> dict[str, RateLimitPolicy]:
    return {
        INCIDENTS_CREATE_POLICY: RateLimitPolicy(
            INCIDENTS_CREATE_POLICY, incidents, 600
        ),
        TRACKING_LOOKUP_POLICY: RateLimitPolicy(
            TRACKING_LOOKUP_POLICY, tracking, 60
        ),
        LOGIN_POLICY: RateLimitPolicy(LOGIN_POLICY, login, 60),
        VOICE_TRANSCRIBE_POLICY: RateLimitPolicy(
            VOICE_TRANSCRIBE_POLICY, voice, 60
        ),
        VOICE_SPEAK_POLICY: RateLimitPolicy(VOICE_SPEAK_POLICY, voice, 60),
        AI_UNDERSTAND_POLICY: RateLimitPolicy(AI_UNDERSTAND_POLICY, ai, 60),
        AI_ANALYZE_IMAGE_POLICY: RateLimitPolicy(
            AI_ANALYZE_IMAGE_POLICY, ai, 60
        ),
    }


def make_limiter(clock: FakeClock, **overrides) -> RateLimiter:
    return RateLimiter(
        InMemoryRateLimitBackend(),
        make_policies(**overrides),
        key_prefix="test:ratelimit",
        clock=clock,
    )


def make_request(
    client_host: str, headers: dict[str, str] | None = None
) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "scheme": "http",
            "server": ("testserver", 80),
            "root_path": "",
            "query_string": b"",
            "headers": raw_headers,
            "client": (client_host, 12345),
        }
    )


class RateLimiterUnitTests(unittest.TestCase):
    def test_below_limit_is_allowed_and_excess_is_denied(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(
            InMemoryRateLimitBackend(),
            {
                INCIDENTS_CREATE_POLICY: RateLimitPolicy(
                    INCIDENTS_CREATE_POLICY, 2, 60
                )
            },
            key_prefix="unit",
            clock=clock,
        )

        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)
        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)

        denied = limiter.check(INCIDENTS_CREATE_POLICY, "client-a")
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.retry_after, 60)

    def test_retry_after_counts_down_and_window_resets(self) -> None:
        clock = FakeClock(1000.0)
        limiter = RateLimiter(
            InMemoryRateLimitBackend(),
            {
                INCIDENTS_CREATE_POLICY: RateLimitPolicy(
                    INCIDENTS_CREATE_POLICY, 2, 60
                )
            },
            key_prefix="unit",
            clock=clock,
        )

        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)
        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)
        self.assertEqual(
            limiter.check(INCIDENTS_CREATE_POLICY, "client-a").retry_after, 60
        )

        clock.advance(20)
        self.assertEqual(
            limiter.check(INCIDENTS_CREATE_POLICY, "client-a").retry_after, 40
        )

        clock.advance(40)
        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)

    def test_client_buckets_are_independent(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(
            InMemoryRateLimitBackend(),
            {
                INCIDENTS_CREATE_POLICY: RateLimitPolicy(
                    INCIDENTS_CREATE_POLICY, 1, 60
                )
            },
            key_prefix="unit",
            clock=clock,
        )

        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)
        self.assertFalse(limiter.check(INCIDENTS_CREATE_POLICY, "client-a").allowed)
        self.assertTrue(limiter.check(INCIDENTS_CREATE_POLICY, "client-b").allowed)

    def test_backend_failure_is_raised(self) -> None:
        limiter = RateLimiter(
            FailingRateLimitBackend(),
            {
                INCIDENTS_CREATE_POLICY: RateLimitPolicy(
                    INCIDENTS_CREATE_POLICY, 1, 60
                )
            },
            key_prefix="unit",
        )

        with self.assertRaises(RateLimitBackendError):
            limiter.check(INCIDENTS_CREATE_POLICY, "client-a")

    def test_build_rate_limiter_returns_memory_limiter(self) -> None:
        limiter = build_rate_limiter(make_settings())
        self.assertIsNotNone(limiter)
        assert limiter is not None
        limiter.close()

    def test_build_rate_limiter_can_be_disabled(self) -> None:
        self.assertIsNone(build_rate_limiter(make_settings(rate_limit_enabled=False)))

    def test_build_policies_uses_configured_limits(self) -> None:
        policies = build_policies(
            make_settings(
                rate_limit_incidents_create_limit=7,
                rate_limit_tracking_lookup_limit=9,
            )
        )

        self.assertEqual(policies[INCIDENTS_CREATE_POLICY].limit, 7)
        self.assertEqual(policies[TRACKING_LOOKUP_POLICY].limit, 9)


class RateLimitConfigTests(unittest.TestCase):
    def test_invalid_backend_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            make_settings(rate_limit_backend="invalid")

    def test_invalid_trusted_proxy_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            make_settings(rate_limit_trusted_proxies="not-an-ip")

    def test_redis_backend_requires_url(self) -> None:
        with self.assertRaises(ValidationError):
            make_settings(
                rate_limit_backend="redis",
                rate_limit_redis_url=None,
            )

    def test_non_positive_limits_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            make_settings(rate_limit_incidents_create_limit=0)
        with self.assertRaises(ValidationError):
            make_settings(rate_limit_tracking_lookup_window_seconds=0)

    def test_production_cannot_disable_rate_limiting(self) -> None:
        with self.assertRaises(ValidationError):
            make_settings(environment="production", rate_limit_enabled=False)

    def test_valid_trusted_proxy_list_is_normalized(self) -> None:
        configured = make_settings(
            rate_limit_trusted_proxies="10.0.0.0/8, 192.168.1.10,::1"
        )

        self.assertEqual(
            configured.rate_limit_trusted_proxies,
            "10.0.0.0/8,192.168.1.10/32,::1/128",
        )
        self.assertEqual(len(configured.rate_limit_trusted_proxy_networks), 3)

    def test_valid_redis_config_is_accepted(self) -> None:
        configured = make_settings(
            rate_limit_backend="redis",
            rate_limit_redis_url="redis://127.0.0.1:6379/0",
        )

        self.assertEqual(configured.rate_limit_backend, "redis")


class TrustedProxyResolutionTests(unittest.TestCase):
    def test_untrusted_peer_ignores_forwarded_headers(self) -> None:
        request = make_request(
            "198.51.100.5",
            {"X-Forwarded-For": "203.0.113.99", "X-Real-IP": "203.0.113.98"},
        )

        self.assertEqual(
            resolve_client_ip(request, "10.0.0.0/8"), "198.51.100.5"
        )

    def test_trusted_peer_uses_rightmost_untrusted_forwarded_address(self) -> None:
        request = make_request(
            "10.0.0.5",
            {"X-Forwarded-For": "203.0.113.99, 10.0.0.2"},
        )

        self.assertEqual(
            resolve_client_ip(request, "10.0.0.0/8"), "203.0.113.99"
        )

    def test_trusted_peer_uses_x_real_ip_without_forwarded_chain(self) -> None:
        request = make_request(
            "10.0.0.5", {"X-Real-IP": "203.0.113.50"}
        )

        self.assertEqual(
            resolve_client_ip(request, "10.0.0.0/8"), "203.0.113.50"
        )

    def test_trusted_peer_falls_back_when_forwarded_chain_is_invalid(self) -> None:
        request = make_request(
            "10.0.0.5", {"X-Forwarded-For": "not-an-ip"}
        )

        self.assertEqual(resolve_client_ip(request, "10.0.0.0/8"), "10.0.0.5")

    def test_all_trusted_chain_uses_leftmost_address(self) -> None:
        request = make_request(
            "10.0.0.5", {"X-Forwarded-For": "10.0.0.2, 10.0.0.3"}
        )

        self.assertEqual(resolve_client_ip(request, "10.0.0.0/8"), "10.0.0.2")


class RateLimitAPITests(unittest.TestCase):
    password = "CorrectHorseBattery9"

    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_rate_limiter, None)
        reset_rate_limiter()
        TEST_ENGINE.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=TEST_ENGINE)
        Base.metadata.create_all(bind=TEST_ENGINE)
        self.clock = FakeClock()
        self.limiter = make_limiter(self.clock)
        app.dependency_overrides[get_rate_limiter] = lambda: self.limiter
        self.client = TestClient(app, client=("203.0.113.10", 50000))

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_rate_limiter, None)
        self.limiter.close()

    def incident_payload(self, **overrides) -> dict[str, object]:
        payload = {
            "category": "pothole",
            "description": "Large pothole near the school gate.",
        }
        payload.update(overrides)
        return payload

    def create_user(
        self,
        *,
        email: str = "dispatcher@example.org",
        role: UserRole | str = UserRole.dispatcher,
    ) -> int:
        with TestingSessionLocal() as db:
            user = auth_service.create_user(
                db,
                email=email,
                password=self.password,
                role=role,
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

    def test_incident_submission_allowed_below_limit_and_429_above(self) -> None:
        for _ in range(2):
            response = self.client.post(
                "/api/v1/incidents", json=self.incident_payload()
            )
            self.assertEqual(response.status_code, 201)

        denied = self.client.post(
            "/api/v1/incidents", json=self.incident_payload()
        )
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(
            denied.json()["detail"],
            "Too many requests. Please try again later.",
        )
        self.assertEqual(denied.headers["Retry-After"], "600")
        self.assertEqual(denied.headers["Cache-Control"], "no-store")

        with TestingSessionLocal() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(Incident)), 2
            )

    def test_tracking_lookup_allowed_below_limit_and_429_above(self) -> None:
        created = self.client.post(
            "/api/v1/incidents", json=self.incident_payload()
        )
        self.assertEqual(created.status_code, 201)
        tracking_id = created.json()["tracking_id"]

        for _ in range(3):
            response = self.client.get(f"/api/v1/tracking/{tracking_id}")
            self.assertEqual(response.status_code, 200)

        denied = self.client.get(f"/api/v1/tracking/{tracking_id}")
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.headers["Retry-After"], "60")

    def test_independent_clients_have_independent_buckets(self) -> None:
        client_a = TestClient(app, client=("203.0.113.10", 50000))
        client_b = TestClient(app, client=("203.0.113.11", 50000))

        for _ in range(2):
            self.assertEqual(
                client_a.post(
                    "/api/v1/incidents", json=self.incident_payload()
                ).status_code,
                201,
            )
            self.assertEqual(
                client_b.post(
                    "/api/v1/incidents", json=self.incident_payload()
                ).status_code,
                201,
            )

        self.assertEqual(
            client_a.post(
                "/api/v1/incidents", json=self.incident_payload()
            ).status_code,
            429,
        )
        self.assertEqual(
            client_b.post(
                "/api/v1/incidents", json=self.incident_payload()
            ).status_code,
            429,
        )

    def test_untrusted_forwarded_headers_cannot_bypass_limit(self) -> None:
        with patch.object(settings, "rate_limit_trusted_proxies", ""):
            for forwarded_ip in ("198.51.100.1", "198.51.100.2"):
                response = self.client.post(
                    "/api/v1/incidents",
                    json=self.incident_payload(),
                    headers={"X-Forwarded-For": forwarded_ip},
                )
                self.assertEqual(response.status_code, 201)

            denied = self.client.post(
                "/api/v1/incidents",
                json=self.incident_payload(),
                headers={"X-Forwarded-For": "198.51.100.3"},
            )
            self.assertEqual(denied.status_code, 429)

    def test_trusted_proxy_uses_forwarded_client_for_buckets(self) -> None:
        with patch.object(
            settings, "rate_limit_trusted_proxies", "10.0.0.0/8"
        ):
            trusted_client = TestClient(app, client=("10.0.0.5", 50000))

            for forwarded_ip in ("203.0.113.1", "203.0.113.1"):
                response = trusted_client.post(
                    "/api/v1/incidents",
                    json=self.incident_payload(),
                    headers={"X-Forwarded-For": forwarded_ip},
                )
                self.assertEqual(response.status_code, 201)

            denied = trusted_client.post(
                "/api/v1/incidents",
                json=self.incident_payload(),
                headers={"X-Forwarded-For": "203.0.113.1"},
            )
            self.assertEqual(denied.status_code, 429)

            for _ in range(2):
                response = trusted_client.post(
                    "/api/v1/incidents",
                    json=self.incident_payload(),
                    headers={"X-Forwarded-For": "203.0.113.2"},
                )
                self.assertEqual(response.status_code, 201)

    def test_login_ip_limit_preserves_account_lockout_behavior(self) -> None:
        user_id = self.create_user()

        for _ in range(2):
            response = self.client.post(
                "/api/v1/auth/login",
                json={
                    "email": "dispatcher@example.org",
                    "password": "wrong-password",
                },
            )
            self.assertEqual(response.status_code, 401)

        denied = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "dispatcher@example.org",
                "password": "wrong-password",
            },
        )
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.headers["Retry-After"], "60")

        with TestingSessionLocal() as db:
            user = db.get(User, user_id)
            assert user is not None
            self.assertEqual(user.failed_login_count, 2)
            self.assertIsNone(user.locked_until)

        self.clock.advance(61)
        self.login()

        with TestingSessionLocal() as db:
            user = db.get(User, user_id)
            assert user is not None
            self.assertEqual(user.failed_login_count, 0)
            self.assertIsNone(user.locked_until)

    def test_staff_workflow_remains_functional(self) -> None:
        self.create_user()
        login_response = self.login()
        csrf_headers = self.csrf_headers(self.csrf_token(login_response))

        created = self.client.post(
            "/api/v1/incidents", json=self.incident_payload()
        )
        self.assertEqual(created.status_code, 201)
        incident_id = created.json()["id"]

        listed = self.client.get("/api/v1/incidents")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(len(listed.json()), 1)

        updated = self.client.patch(
            f"/api/v1/incidents/{incident_id}",
            json={"status": "In Progress"},
            headers=csrf_headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "In Progress")

    def test_limiter_backend_failure_returns_generic_503(self) -> None:
        failing_limiter = RateLimiter(
            FailingRateLimitBackend(),
            make_policies(),
            key_prefix="test:failing",
            clock=self.clock,
        )
        app.dependency_overrides[get_rate_limiter] = lambda: failing_limiter

        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": "dispatcher@example.org",
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Rate limiting is temporarily unavailable. Please try again later.",
        )
        self.assertNotIn("retry-after", response.headers)
        self.assertNotIn("redis", response.text.lower())
        self.assertNotIn("backend", response.text.lower())
        self.assertNotIn("203.0.113", response.text)

    def test_client_supplied_tracking_id_is_rejected(self) -> None:
        rejected = self.client.post(
            "/api/v1/incidents",
            json=self.incident_payload(tracking_id="CP-CLIENT-OVERRIDE"),
        )
        self.assertEqual(rejected.status_code, 422)

        created = self.client.post(
            "/api/v1/incidents", json=self.incident_payload()
        )
        self.assertEqual(created.status_code, 201)
        tracking_id = created.json()["tracking_id"]
        self.assertTrue(tracking_id.startswith("CP-"))
        self.assertNotEqual(tracking_id, "CP-CLIENT-OVERRIDE")

        with TestingSessionLocal() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(Incident)), 1
            )

    def test_duplicate_submissions_get_unique_server_tracking_ids(self) -> None:
        first = self.client.post(
            "/api/v1/incidents", json=self.incident_payload()
        )
        second = self.client.post(
            "/api/v1/incidents", json=self.incident_payload()
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(
            first.json()["tracking_id"], second.json()["tracking_id"]
        )

    def test_provider_endpoint_is_rate_limited(self) -> None:
        for _ in range(2):
            response = self.client.post(
                "/api/v1/ai/understand",
                json={"text": "Large pothole near the school gate."},
            )
            self.assertEqual(response.status_code, 200)

        denied = self.client.post(
            "/api/v1/ai/understand",
            json={"text": "Large pothole near the school gate."},
        )
        self.assertEqual(denied.status_code, 429)


if __name__ == "__main__":
    unittest.main()
