import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://unused:unused@127.0.0.1/unused",
)
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "synthetic-test-key-for-hs256-at-least-32-bytes",
)
os.environ.setdefault("APP_NAME", "BorderGroup Test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")

from app.api.departments import router as departments_router
from app.core.security import create_access_token
from app.database.db_connection import get_db
from app.services.department_services import DepartmentService


class DepartmentsAccessTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock(info={})
        app = FastAPI()
        app.include_router(departments_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_all_routes_reject_requests_without_token(self):
        requests = [
            ("GET", "/api/departments", None),
            ("GET", "/api/departments/P01", None),
            ("POST", "/api/departments", {
                "id": "P01",
                "name": "Тестовий підрозділ",
                "department_type": "Тест",
            }),
            ("PATCH", "/api/departments/P01", {"name": "Нова назва"}),
            ("DELETE", "/api/departments/P01", None),
        ]

        for method, path, payload in requests:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, json=payload)
                self.assertEqual(response.status_code, 401)

    def test_all_routes_reject_non_admin(self):
        self.db.get.return_value = SimpleNamespace(id=7, role_id="VYK")
        token = create_access_token(7)
        headers = {"Authorization": f"Bearer {token}"}

        requests = [
            ("GET", "/api/departments", None),
            ("GET", "/api/departments/P01", None),
            ("POST", "/api/departments", {
                "id": "P01",
                "name": "Тестовий підрозділ",
                "department_type": "Тест",
            }),
            ("PATCH", "/api/departments/P01", {"name": "Нова назва"}),
            ("DELETE", "/api/departments/P01", None),
        ]

        for method, path, payload in requests:
            with self.subTest(method=method, path=path):
                response = self.client.request(
                method, path, json=payload, headers=headers
                )
                self.assertEqual(response.status_code, 403)
    def test_admin_can_access_all_routes(self):
        self.db.get.return_value = SimpleNamespace(id=7, role_id="ADMIN")
        token = create_access_token(7)
        headers = {"Authorization": f"Bearer {token}"}

        department = SimpleNamespace(
            id="P01",
            name="Тестовий підрозділ",
            department_type="Тест",
            notes="",
        )
        payload = {
            "id": "P01",
            "name": "Тестовий підрозділ",
            "department_type": "Тест",
        }

        cases = [
            ("GET", "/api/departments", None, "get_all", [department], 200),
            ("GET", "/api/departments/P01", None, "get_by_id", department, 200),
            ("POST", "/api/departments", payload, "create", department, 201),
            (
                "PATCH",
                "/api/departments/P01",
                {"name": "Нова назва"},
                "update",
                department,
                200,
            ),
            ("DELETE", "/api/departments/P01", None, "delete", None, 204),
        ]

        for method, path, body, service_method, result, expected in cases:
            with self.subTest(method=method, path=path):
                with patch.object(
                    DepartmentService, service_method, return_value=result
                ) as service_call:
                    response = self.client.request(
                        method, path, json=body, headers=headers
                    )

                self.assertEqual(response.status_code, expected)
                service_call.assert_called_once()