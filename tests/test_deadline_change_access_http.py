import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes")

from app.api.deadline_changes import router as changes_router
from app.core.security import create_access_token
from app.database.db_connection import get_db
from app.models.measure import Measure
from app.models.program import Program
from app.models.user import User

BODY = {"measure_id": "Z-01", "decision_date": "2026-11-20", "previous_deadline": "2026-11-30",
        "new_deadline": "2026-12-15", "reason": "Наказ № 15 від 20.11.2026"}
CREATED = {"id": 1, "user_id": 7, **BODY}


class DeadlineChangeAccessTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock(info={})
        app = FastAPI()
        app.include_router(changes_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def as_user(self, role_id, program_owner_id=None, program_id=None):
        user = SimpleNamespace(id=7, role_id=role_id, program_id=program_id)
        measure = SimpleNamespace(id="Z-01", program_id="P1", deadline_type="date", deadline_on=date(2026, 11, 30))
        program = SimpleNamespace(id="P1", created_by_user_id=program_owner_id)
        self.db.get.side_effect = lambda model, key: {User: user, Measure: measure, Program: program}.get(model)
        return {"Authorization": f"Bearer {create_access_token(7)}"}

    def post(self, headers):
        with patch("app.api.deadline_changes.DeadlineChangeService") as service:
            service.return_value.create_change.return_value = CREATED
            return self.client.post("/api/deadline-changes/", json=BODY, headers=headers)

    def test_main_coordinator_owner_can_postpone(self):
        self.assertEqual(self.post(self.as_user("MAIN_KOORD", program_owner_id=7)).status_code, 201)

    def test_main_coordinator_of_other_program_cannot(self):
        self.assertEqual(self.post(self.as_user("MAIN_KOORD", program_owner_id=99)).status_code, 403)

    def test_executor_and_manager_cannot(self):
        for role in ("VYK", "KER"):
            with self.subTest(role=role):
                self.assertEqual(self.post(self.as_user(role, program_owner_id=7)).status_code, 403)

    def test_admin_can_postpone(self):
        self.assertEqual(self.post(self.as_user("ADMIN")).status_code, 201)

    def test_new_deadline_must_be_later(self):
        headers = self.as_user("MAIN_KOORD", program_owner_id=7)
        bad = {**BODY, "new_deadline": "2026-11-01"}
        self.assertEqual(self.client.post("/api/deadline-changes/", json=bad, headers=headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()
