import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes")

from app.api.action_logs import router as logs_router
from app.core.security import create_access_token
from app.database.db_connection import get_db

LOG = SimpleNamespace(
    id="log-1", occurred_at=datetime(2026, 11, 20, 17, 0, 0), action="update",
    entity_type="executions", entity_id="12", field_name="status",
    old_value="pending", new_value="approved",
)
USER = SimpleNamespace(id=3, login="koord.d1", role_id="KOORD", position="Координатор", department_id="D1")
DEPT = SimpleNamespace(id="D1", name="Департамент 1")


class ActionLogFeedHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock(info={})
        app = FastAPI()
        app.include_router(logs_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers_for(self, role_id):
        self.db.get.return_value = SimpleNamespace(id=1, role_id=role_id)
        return {"Authorization": f"Bearer {create_access_token(1)}"}

    def test_feed_requires_token(self):
        self.assertEqual(self.client.get("/api/action-logs/feed").status_code, 401)

    def test_feed_is_admin_only(self):
        for role in ("MAIN_KOORD", "KOORD", "VYK", "KER"):
            with self.subTest(role=role):
                response = self.client.get("/api/action-logs/feed", headers=self.headers_for(role))
                self.assertEqual(response.status_code, 403)

    def test_feed_returns_actor_department_and_total(self):
        with patch("app.api.action_logs.ActionLogFeedRepository") as repo:
            repo.return_value.page.return_value = (41, [(LOG, USER, DEPT), (LOG, None, None)])
            response = self.client.get(
                "/api/action-logs/feed",
                params={"page": 2, "page_size": 25, "q": "koord", "department_id": "D1"},
                headers=self.headers_for("ADMIN"),
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["total"], body["page"], body["page_size"]), (41, 2, 25))
        first, system = body["items"]
        self.assertEqual(first["actor"]["login"], "koord.d1")
        self.assertEqual(first["actor"]["department_name"], "Департамент 1")
        self.assertEqual((first["old_value"], first["new_value"]), ("pending", "approved"))
        self.assertIsNone(system["actor"])
        kwargs = repo.return_value.page.call_args.kwargs
        self.assertEqual((kwargs["page"], kwargs["q"], kwargs["department_id"]), (2, "koord", "D1"))

    def test_feed_is_not_captured_by_log_id_route(self):
        with patch("app.api.action_logs.ActionLogFeedRepository") as repo:
            repo.return_value.page.return_value = (0, [])
            repo.return_value.facets.return_value = (["create"], ["users"])
            headers = self.headers_for("ADMIN")
            self.assertEqual(self.client.get("/api/action-logs/feed", headers=headers).status_code, 200)
            facets = self.client.get("/api/action-logs/facets", headers=headers)
        self.assertEqual(facets.json(), {"actions": ["create"], "entity_types": ["users"]})

    def test_feed_validates_parameters(self):
        headers = self.headers_for("ADMIN")
        self.assertEqual(self.client.get("/api/action-logs/feed", params={"page_size": 500}, headers=headers).status_code, 422)
        self.assertEqual(self.client.get("/api/action-logs/feed", params={"page": 0}, headers=headers).status_code, 422)
        self.assertEqual(self.client.get("/api/action-logs/feed", params={
            "since": "2026-11-20T10:00:00", "until": "2026-11-19T10:00:00"}, headers=headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()
