"""Regression tests for the Phase 3C-2A removal of the legacy complaints API.

The legacy ``/api/v1/complaints`` routes targeted a ``complaints`` table that
does not exist in the live MySQL schema. They are removed entirely, so these
tests prove the paths now return a plain ``404`` instead of a misleading
"database unavailable" ``503`` and that the active incident/tracking workflow
is still registered.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.database import Base
from app.main import app

DATABASE_UNAVAILABLE_FRAGMENT = "Database unavailable"


class LegacyComplaintsRemovedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_legacy_complaint_paths_are_not_registered(self) -> None:
        cases = (
            ("get", "/api/v1/complaints", None),
            ("post", "/api/v1/complaints", {}),
            ("get", "/api/v1/complaints/1", None),
            ("patch", "/api/v1/complaints/1", {"status": "in_progress"}),
        )

        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                kwargs = {"json": body} if body is not None else {}
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(DATABASE_UNAVAILABLE_FRAGMENT, response.text)

    def test_orm_metadata_matches_the_live_schema(self) -> None:
        # SQLite test setup creates tables from this metadata, so an accidental
        # re-registration of the legacy model would silently reintroduce a table
        # that does not exist in production.
        self.assertNotIn("complaints", Base.metadata.tables)
        self.assertIn("incidents", Base.metadata.tables)

    def test_openapi_no_longer_documents_complaints(self) -> None:
        spec = self.client.get("/openapi.json").json()

        complaint_paths = [path for path in spec["paths"] if "complaint" in path]
        self.assertEqual(complaint_paths, [])
        self.assertNotIn("complaints", spec.get("tags", []))

    def test_active_incident_and_tracking_routes_remain(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertIn("/api/v1/incidents", paths)
        self.assertIn("post", paths["/api/v1/incidents"])
        self.assertIn("get", paths["/api/v1/incidents"])

        incident_detail = "/api/v1/incidents/{incident_id}"
        self.assertIn(incident_detail, paths)
        self.assertIn("get", paths[incident_detail])
        self.assertIn("patch", paths[incident_detail])

        tracking = "/api/v1/tracking/{tracking_id}"
        self.assertIn(tracking, paths)
        self.assertIn("get", paths[tracking])


if __name__ == "__main__":
    unittest.main()
