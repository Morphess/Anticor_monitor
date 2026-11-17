import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes")

from app.api.auth import router as auth_router
from app.core.config import settings
from app.core.security import hash_password
from app.database.db_connection import get_db


class AuthHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user = SimpleNamespace(
            id=7,
            password_hash=hash_password("demo-password"),
        )

    def setUp(self):
        self.db = Mock()
        app = FastAPI()
        app.include_router(auth_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_valid_credentials_return_token(self):
        self.db.scalar.return_value = self.user

        response = self.client.post(
            "/api/auth/token",
            data={"username": "demo-user", "password": "demo-password"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        claims = jwt.decode(
            body["access_token"], settings.JWT_SECRET_KEY, algorithms=["HS256"]
        )
        self.assertEqual(claims["sub"], "7")

    def test_wrong_password_returns_401(self):
        self.db.scalar.return_value = self.user

        response = self.client.post(
            "/api/auth/token",
            data={"username": "demo-user", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access_token", response.json())

    def test_unknown_user_returns_401(self):
        self.db.scalar.return_value = None

        response = self.client.post(
            "/api/auth/token",
            data={"username": "unknown", "password": "demo-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access_token", response.json())