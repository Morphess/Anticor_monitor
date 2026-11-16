"""Вхід, сесії та рольова модель доступу (п'ять ролей — як у завданні й наборі організаторів)."""
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request

from .db import session
from .models import User

# Куди потрапляє користувач після входу
HOME_BY_ROLE = {"VYK": "/my", "KOORD": "/review", "KER": "/panel", "ANAL": "/panel", "ADMIN": "/admin"}
# Хто бачить усю програму (а не лише власні заходи)
SEES_ALL = ("KOORD", "KER", "ANAL", "ADMIN")
_ITERATIONS = 200_000


class LoginRequired(Exception):
    """Користувач не увійшов — перенаправляємо на сторінку входу."""


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS).hex()
    return f"pbkdf2${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    try:
        _, iterations, salt, digest = (stored or "").split("$")
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(check, digest)


def user_dict(u: User) -> dict:
    return {"id": u.id, "role": u.role, "unit_id": u.unit_id, "unit_name": u.unit.name if u.unit else "",
            "position": u.position, "active": u.active}


def current_user(request: Request) -> dict:
    uid = request.session.get("uid")
    if not uid:
        raise LoginRequired
    user = session().get(User, uid)
    if not user or not user.active:
        request.session.clear()
        raise LoginRequired
    return user_dict(user)


def require_role(*roles: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Недостатньо прав для цієї сторінки")
        return user

    return dependency


executor_only = require_role("VYK")
coordinator_only = require_role("KOORD")
admin_only = require_role("ADMIN")
sees_all = require_role(*SEES_ALL)


def can_view_measure(user: dict, measure: dict) -> bool:
    """Виконавець бачить лише власні заходи; решта ролей — усі."""
    return user["role"] in SEES_ALL or measure["executor_id"] == user["id"]
