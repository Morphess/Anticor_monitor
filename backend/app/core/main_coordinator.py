"""Перевірки доступу для окремої системної ролі MAIN_KOORD."""
from fastapi import Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.models.user import User


def require_main_coordinator(
    user: User = Depends(get_current_user),
) -> User:
    """Пропускає тільки MAIN_KOORD; ADMIN і звичайний KOORD не можуть створювати програми."""
    if user.role_id != "MAIN_KOORD":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ця дія доступна лише головному координатору (MAIN_KOORD)",
        )
    return user


def require_main_or_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Читання глобального довідника; операції створення доступні лише MAIN_KOORD."""
    if user.role_id not in {"MAIN_KOORD", "ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ лише для MAIN_KOORD або ADMIN",
        )
    return user
