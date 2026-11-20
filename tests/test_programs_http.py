import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes"
)

from app.core.dependencies import get_current_user
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError
from app.api.programs import router as programs_router
from app.database.db_connection import get_db
from app.repositories.program_repository import ProgramRepository
from app.services.program_services import ProgramService


PROGRAM = {
    "id": "TEST-2026",
    "title": "Синтетична тестова програма",
    "organization_name": "Тестова організація",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
    "approval_reference": "TEST-ORDER",
    "approval_status": "approved",
    "has_restricted_information": False,
    "coordinator_department_id": None,
    "goals": "Перевірка API",
    "notes": "",
}


class ProgramsHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock(info={})
        app = FastAPI()
        app.include_router(programs_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.actor = SimpleNamespace(id=7, role_id="MAIN_KOORD", department_id="D01")
        app.dependency_overrides[get_current_user] = lambda: self.actor
        self.db.get.return_value = SimpleNamespace(created_by_user_id=7)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_admin_cannot_create_program(self):
        self.actor.role_id = "ADMIN"
        response = self.client.post("/api/programs", json=PROGRAM)
        self.assertEqual(response.status_code, 403)
        self.db.add.assert_not_called()

    def test_non_owner_cannot_update_program(self):
        self.db.get.return_value = SimpleNamespace(created_by_user_id=99)
        response = self.client.patch("/api/programs/TEST-2026", json={"title": "New"})
        self.assertEqual(response.status_code, 403)

    def test_list_returns_200(self):
        self.db.scalars.return_value = [PROGRAM]
        with patch.object(ProgramWorkflowService, "my_programs", return_value=[{"id": "TEST-2026"}]):
            response = self.client.get("/api/programs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id"], "TEST-2026")

    def test_missing_program_returns_404(self):
        with patch.object(ProgramWorkflowService, "visible_program", side_effect=WorkflowError(404, "Missing")):
            response = self.client.get("/api/programs/ABSENT")

        self.assertEqual(response.status_code, 404)

    def test_create_returns_201(self):
        with patch("app.api.programs.Program", return_value=SimpleNamespace(**PROGRAM)):
            response = self.client.post("/api/programs", json=PROGRAM)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "TEST-2026")

    def test_invalid_dates_return_422(self):
        invalid = {**PROGRAM, "start_date": "2026-12-31", "end_date": "2026-01-01"}

        response = self.client.post("/api/programs", json=invalid)

        self.assertEqual(response.status_code, 422)

    def test_update_returns_200(self):
        updated = {**PROGRAM, "title": "Оновлена тестова програма"}
        with patch.object(ProgramService, "update", return_value=updated):
            response = self.client.patch(
                "/api/programs/TEST-2026",
                json={"title": "Оновлена тестова програма"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Оновлена тестова програма")

    def test_update_missing_program_returns_404(self):
        self.db.get.return_value = None
        with patch.object(ProgramRepository, "get_by_id", return_value=None):
            response = self.client.patch(
                "/api/programs/ABSENT", json={"title": "Нова назва"}
            )

        self.assertEqual(response.status_code, 404)

    def test_delete_returns_204(self):
        with patch.object(ProgramService, "delete") as delete_program:
            response = self.client.delete("/api/programs/TEST-2026")

        self.assertEqual(response.status_code, 204)
        delete_program.assert_called_once_with("TEST-2026")

    def test_delete_missing_program_returns_404(self):
        self.db.get.return_value = None
        with patch.object(ProgramRepository, "get_by_id", return_value=None):
            response = self.client.delete("/api/programs/ABSENT")

        self.assertEqual(response.status_code, 404)
