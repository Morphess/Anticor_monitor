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

from app.api.sections import router as sections_router
from app.core.security import create_access_token
from app.database.db_connection import get_db
from app.services.section_services import SectionNotFoundError, SectionService


class SectionsHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock(info={})
        app = FastAPI()
        app.include_router(sections_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers_for(self, role_id):
        self.db.get.return_value = SimpleNamespace(id=7, role_id=role_id)
        token = create_access_token(7)
        return {"Authorization": f"Bearer {token}"}

    def test_list_without_token_returns_401(self):
        response = self.client.get("/api/sections/")
        self.assertEqual(response.status_code, 401)

    def test_member_cannot_list_sections(self):
        response = self.client.get("/api/sections/", headers=self.headers_for("VYKON"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_sections(self):
        with patch.object(SectionService, "list_sections", return_value=[]):
            response = self.client.get(
                "/api/sections/", headers=self.headers_for("ADMIN")
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_admin_can_create_section(self):
        section = SimpleNamespace(id="R1", number=1, title="Тестовий розділ")
        with patch.object(SectionService, "create_section", return_value=section):
            response = self.client.post(
                "/api/sections/",
                json={"id": "R1", "number": 1, "title": "Тестовий розділ"},
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "R1")

    def test_mismatched_section_number_returns_422(self):
        response = self.client.post(
            "/api/sections/",
            json={"id": "R1", "number": 2, "title": "Тестовий розділ"},
            headers=self.headers_for("ADMIN"),
        )
        self.assertEqual(response.status_code, 422)

    def test_missing_section_returns_404(self):
        with patch.object(
            SectionService,
            "get_section",
            side_effect=SectionNotFoundError("Розділ не знайдено"),
        ):
            response = self.client.get(
                "/api/sections/R1", headers=self.headers_for("ADMIN")
            )

        self.assertEqual(response.status_code, 404)

    def test_admin_can_update_section(self):
        updated = SimpleNamespace(id="R1", number=1, title="Оновлений розділ")
        with patch.object(SectionService, "update_section", return_value=updated):
            response = self.client.patch(
                "/api/sections/R1",
                json={"title": "Оновлений розділ"},
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Оновлений розділ")

    def test_update_missing_section_returns_404(self):
        with patch.object(
            SectionService,
            "update_section",
            side_effect=SectionNotFoundError("Розділ не знайдено"),
        ):
            response = self.client.patch(
                "/api/sections/ABSENT",
                json={"title": "Оновлений розділ"},
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 404)
