from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from app.core.config import settings


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Створення JWT-токена на 1 годину
def create_access_token(user_id: int) -> str:

    data = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)}

    return jwt.encode(data, settings.JWT_SECRET_KEY, algorithm="HS256")
