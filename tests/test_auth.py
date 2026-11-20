import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
from fastapi import HTTPException

os.environ.setdefault("APP_NAME", "BorderGroup test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes"
)

from app.api.auth import login
from app.core.config import settings
from app.core.security import hash_password


class AuthFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.user = SimpleNamespace(
            id=7,
            role_id="VYK",
            password_hash=hash_password("demo-password"),
        )

    def test_valid_password_returns_token(self) -> None:
        db = Mock()
        db.scalar.return_value = self.user

        result = login(
            SimpleNamespace(username="demo-user", password="demo-password"),
            db,
        )

        self.assertEqual(result["token_type"], "bearer")
        claims = jwt.decode(
            result["access_token"],
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
        )
        self.assertEqual(claims["sub"], "7")

    def test_wrong_password_returns_401(self) -> None:
        db = Mock()
        db.scalar.return_value = self.user

        with self.assertRaises(HTTPException) as error:
            login(SimpleNamespace(username="demo-user", password="wrong"), db)

        self.assertEqual(error.exception.status_code, 401)

    def test_unknown_user_returns_401(self) -> None:
        db = Mock()
        db.scalar.return_value = None

        with self.assertRaises(HTTPException) as error:
            login(SimpleNamespace(username="unknown", password="anything"), db)

        self.assertEqual(error.exception.status_code, 401)