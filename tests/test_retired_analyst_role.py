"""Retiring ANAL preserves historical rows but prevents new assignments and login."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

for key, value in {"APP_NAME":"Test", "DEBUG":"false", "SQL_ECHO":"false",
                   "DATABASE_URL":"postgresql+psycopg://unused:unused@127.0.0.1/unused",
                   "JWT_SECRET_KEY":"synthetic-test-key-at-least-32-bytes"}.items():
    os.environ.setdefault(key, value)
from app.api.auth import router
from app.database.db_connection import get_db
from app.schemas.users import UserCreate, UserUpdate
from app.core.security import create_access_token


class RetiredAnalystTests(unittest.TestCase):
    def test_new_assignments_are_rejected(self):
        with self.assertRaises(ValidationError):
            UserCreate(login="synthetic", password="synthetic-password-only", role_id="ANAL")
        with self.assertRaises(ValidationError):
            UserUpdate(role_id="ANAL")

    def setUp(self):
        self.db = Mock(info={})
        user = SimpleNamespace(id=7, role_id="ANAL", password_hash="synthetic")
        self.db.scalar.return_value = user
        self.db.get.return_value = user
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_old_token_cannot_access_profile(self):
        response = self.client.get("/api/auth/me", headers={"Authorization": "Bearer "+create_access_token(7)})
        self.assertEqual(response.status_code, 403)

    def test_correct_password_does_not_reenable_role(self):
        with patch("app.api.auth.verify_password", return_value=True):
            response = self.client.post("/api/auth/token", data={"username":"synthetic", "password":"synthetic"})
        self.assertEqual(response.status_code, 403)
