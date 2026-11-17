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

from app.api.users import router as users_router
from app.core.security import create_access_token
from app.database.db_connection import get_db
from app.services.user_services import (
    UserAlreadyExistsError,
    UserNotFoundError,
    UserService,
)

USER = {
    "id": 8,
    "login": "synthetic.user",
    "role_id": "VYKON",
    "program_id": None,
    "department_id": None,
    "position": None,
}

NEW_USER = {
    "login": "synthetic.user",
    "password": "synthetic-password-123",
    "role_id": "VYKON",
}

class UsersAccessHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        app = FastAPI()
        app.include_router(users_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers_for(self, role_id):
        self.db.get.return_value = SimpleNamespace(id=7, role_id=role_id)
        token = create_access_token(7)
        return {"Authorization": f"Bearer {token}"}

    def test_list_without_token_returns_401(self):
        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, 401)

    def test_member_cannot_list_users(self):
        response = self.client.get(
            "/api/users/", headers=self.headers_for("VYKON")
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_users(self):
        with patch.object(UserService, "list_users", return_value=[]):
            response = self.client.get(
                "/api/users/", headers=self.headers_for("ADMIN")
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_admin_can_create_user(self):
        with patch.object(UserService, "create_user", return_value=USER):
            response = self.client.post(
                "/api/users/",
                json=NEW_USER,
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["login"], "synthetic.user")
        self.assertNotIn("password", response.json())

    def test_invalid_login_returns_422(self):
        response = self.client.post(
            "/api/users/",
            json={**NEW_USER, "login": "bad login"},
            headers=self.headers_for("ADMIN"),
        )
        self.assertEqual(response.status_code, 422)

    def test_duplicate_login_returns_409(self):
        with patch.object(
            UserService,
            "create_user",
            side_effect=UserAlreadyExistsError("Логін зайнятий"),
        ):
            response = self.client.post(
                "/api/users/",
                json=NEW_USER,
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 409)

    def test_missing_user_returns_404(self):
        with patch.object(
            UserService,
            "get_user",
            side_effect=UserNotFoundError("Користувача не знайдено"),
        ):
            response = self.client.get(
                "/api/users/999", headers=self.headers_for("ADMIN")
            )

        self.assertEqual(response.status_code, 404)

    def test_admin_can_update_user(self):
        updated = {**USER, "position": "Тестова посада"}
        with patch.object(UserService, "update_user", return_value=updated):
            response = self.client.patch(
                "/api/users/8",
                json={"position": "Тестова посада"},
                headers=self.headers_for("ADMIN"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["position"], "Тестова посада")

    def test_admin_can_delete_user(self):
        with patch.object(UserService, "delete_user") as delete_user:
            response = self.client.delete(
                "/api/users/8", headers=self.headers_for("ADMIN")
            )

        self.assertEqual(response.status_code, 204)
        delete_user.assert_called_once_with(8)