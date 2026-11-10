import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import ComplaintCategory, Priority, Severity
from app.services.classification.base import ClassificationResult


class AIUnderstandAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_deterministic_endpoint_returns_extended_contract(self) -> None:
        response = self.client.post(
            "/api/v1/ai/understand",
            json={
                "text": "Large pothole near the school gate.",
                "language": "en",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["category"], "pothole")
        self.assertEqual(payload["severity"], "high")
        self.assertEqual(payload["priority"], "high")
        self.assertEqual(payload["responsible_department"], "Road Department")
        self.assertEqual(payload["location_hint"], "school gate")
        self.assertIn("pothole", payload["matched_keywords"])
        self.assertIn("school", payload["severity_signals"])
        self.assertFalse(payload["needs_review"])
        self.assertEqual(payload["provider"], "deterministic_rules")
        self.assertIsNone(payload["confidence"])
        self.assertIn("Deterministic keyword rules", payload["explanation"])
        self.assertEqual(payload["description"], "Large pothole near the school gate.")
        self.assertEqual(payload["summary"], "Large pothole near the school gate.")

    def test_blank_text_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/ai/understand",
            json={"text": "   "},
        )

        self.assertEqual(response.status_code, 422)

    def test_unsupported_language_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/ai/understand",
            json={"text": "pothole near school", "language": "xx"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Unsupported language", response.json()["detail"])

    def test_overlong_text_is_rejected(self) -> None:
        response = self.client.post(
            "/api/v1/ai/understand",
            json={"text": "x" * 4001},
        )

        self.assertEqual(response.status_code, 422)

    def test_mocked_provider_response_is_mapped_by_the_route(self) -> None:
        fake_result = ClassificationResult(
            provider="mock_provider",
            summary="Garbage near the market.",
            description="Garbage near the market.",
            category=ComplaintCategory.garbage,
            severity=Severity.medium,
            priority=Priority.medium,
            responsible_department="Sanitation Department",
            language="en",
            location_hint="market",
            matched_keywords=("garbage",),
            severity_signals=(),
            explanation="Mock provider response for route mapping.",
            needs_review=False,
            confidence=None,
        )

        with patch("app.routes.ai.get_classification_service") as get_service:
            get_service.return_value.classify.return_value = fake_result
            response = self.client.post(
                "/api/v1/ai/understand",
                json={"text": "Garbage near the market.", "language": "en"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "mock_provider")
        self.assertEqual(payload["category"], "garbage")
        self.assertEqual(payload["responsible_department"], "Sanitation Department")
        self.assertEqual(payload["location_hint"], "market")
        self.assertEqual(
            payload["explanation"], "Mock provider response for route mapping."
        )
        get_service.return_value.classify.assert_called_once_with(
            text="Garbage near the market.", language="en"
        )


if __name__ == "__main__":
    unittest.main()
