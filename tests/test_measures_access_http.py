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

from app.api.measures import router as measures_router
from app.core.security import create_access_token
from app.database.db_connection import get_db
from app.services.measure_services import MeasureError, MeasureService

MEASURE = {
    "id": "M-1",
    "program_id": "TEST-2026",
    "section_id": "R1",
    "sequence_number": 1,
    "description": "Тестовий захід",
    "deadline_description": "Постійно",
    "deadline_type": "ongoing",
    "completion_indicator": "Виконано",
    "required_evidence": "Тестовий документ",
    "resources": "Тестові ресурси",
}


class MeasuresAccessHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock(info={})
        app = FastAPI()
        app.include_router(measures_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers_for(self, role_id):
        self.db.get.return_value = SimpleNamespace(id=7, role_id=role_id)
        token = create_access_token(7)
        return {"Authorization": f"Bearer {token}"}

    def test_list_without_token_returns_401(self):
        response = self.client.get("/api/measures/")
        self.assertEqual(response.status_code, 401)

    def test_member_can_list_measures(self):
        with patch.object(MeasureService, "list_measures", return_value=[]):
            response = self.client.get(
                "/api/measures/", headers=self.headers_for("VYKON")
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_member_cannot_delete_measure(self):
        response = self.client.delete(
            "/api/measures/M-1", headers=self.headers_for("VYKON")
        )
        self.assertEqual(response.status_code, 403)

    def test_coordinator_can_delete_measure(self):
        with patch.object(MeasureService, "delete_measure") as delete_measure:
            response = self.client.delete(
                "/api/measures/M-1", headers=self.headers_for("KOORD")
            )

        self.assertEqual(response.status_code, 204)
        delete_measure.assert_called_once_with("M-1")

    def test_admin_can_create_measure(self):
        with patch.object(MeasureService, "create_measure", return_value=MEASURE):
            response = self.client.post(
                "/api/measures/",
                json=MEASURE,
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "M-1")

    def test_date_deadline_without_date_returns_422(self):
        invalid = {**MEASURE, "deadline_type": "date"}

        response = self.client.post(
            "/api/measures/",
            json=invalid,
            headers=self.headers_for("ADMIN"),
        )

        self.assertEqual(response.status_code, 422)

    def test_coordinator_can_update_measure(self):
        updated = {**MEASURE, "description": "Оновлений захід"}
        with patch.object(MeasureService, "update_measure", return_value=updated):
            response = self.client.patch(
                "/api/measures/M-1",
                json={"description": "Оновлений захід"},
                headers=self.headers_for("KOORD"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["description"], "Оновлений захід")

    def test_update_missing_measure_returns_404(self):
        with patch.object(
            MeasureService,
            "update_measure",
            side_effect=MeasureError("Захід не знайдено", 404),
        ):
            response = self.client.patch(
                "/api/measures/ABSENT",
                json={"description": "Оновлений захід"},
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 404)
