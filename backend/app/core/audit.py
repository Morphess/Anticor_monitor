"""Централізований аудит змін SQLAlchemy ORM.

Реєструйте один раз у main.py: enable_audit().
Поточний користувач: db.info['audit_actor_id'] = user.id
у get_current_user().

Кожен запис аудиту пишеться тією самою транзакцією,
що й зміна даних.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import json

from sqlalchemy import event, inspect, insert, select
from sqlalchemy.orm import Mapper, object_session

from app.models.action_log import ActionLog


_ENABLED = False
_REDACTED = "[REDACTED]"
_MAX_VALUE_LENGTH = 4000


# Поля, значення яких не можна записувати у журнал
_SENSITIVE_NAMES = {
    "password",
    "password_hash",
    "secret",
    "secret_key",
    "api_key",
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "private_key",
    "client_secret",
    "recovery_code",
}


# Перевірка, чи містить поле секретну інформацію
def _is_sensitive(name: str) -> bool:

    name = name.lower()

    return (
        name in _SENSITIVE_NAMES
        or "password" in name
        or "secret" in name
        or name.endswith("_token")
        or name.endswith("_private_key")
    )


# Перетворення значення на текст
def _text(value: object) -> str | None:

    if value is None:
        return None

    if isinstance(value, (datetime, Decimal)):
        result = str(value)

    elif isinstance(value, (str, int, float, bool)):
        result = str(value)

    else:
        result = json.dumps(value, ensure_ascii=False, default=str)

    if len(result) > _MAX_VALUE_LENGTH:
        return result[:_MAX_VALUE_LENGTH] + "…[truncated]"

    return result


# Отримання ID об'єкта
def _entity_id(mapper: Mapper, target: object) -> str:

    # Підтримує простий і складений первинний ключ
    key_parts = [str(getattr(target, col.key)) for col in mapper.primary_key]

    result = "|".join(key_parts)

    # У моделі ActionLog entity_id має VARCHAR(50)
    if len(result) > 50:
        raise ValueError("Довжина ключа об'єкта перевищує 50 символів")

    return result


# Отримання ID користувача з SQLAlchemy Session
def _actor_user_id(target: object) -> int | None:

    session = object_session(target)

    if session is None:
        return None

    return session.info.get("audit_actor_id")


# Створення запису аудиту
def _record(
    mapper: Mapper,
    connection,
    target: object,
    *,
    action: str,
    field_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:

    # Не журналюємо сам журнал
    if isinstance(target, ActionLog):
        return

    table_name = mapper.local_table.name

    if len(table_name) > 50:
        raise ValueError("Назва таблиці задовга для ActionLog.entity_type")

    # Запис у тій самій транзакції
    connection.execute(
        insert(ActionLog.__table__).values(
            id=str(uuid4()),
            occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
            actor_user_id=_actor_user_id(target),
            action=action,
            entity_type=table_name,
            entity_id=_entity_id(mapper, target),
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
        )
    )


# Автоматичне журналювання створення запису
def _after_insert(mapper: Mapper, connection, target: object) -> None:

    _record(mapper, connection, target, action="create")


# Автоматичне журналювання редагування
def _before_update(mapper: Mapper, connection, target: object) -> None:

    if isinstance(target, ActionLog):
        return

    state = inspect(target)

    # Шукаємо поля, які змінилися
    changed = [
        col
        for col in mapper.columns
        if (not col.primary_key and state.attrs[col.key].history.has_changes())
    ]

    if not changed:
        return

    pk_values = state.identity

    if pk_values is None:
        return

    criteria = [pk == value for pk, value in zip(mapper.primary_key, pk_values)]

    # Отримуємо старі значення до SQL UPDATE
    old_row = connection.execute(select(*changed).where(*criteria)).mappings().first()

    if old_row is None:
        return

    # Для кожного зміненого поля створюємо запис
    for col in changed:

        old = old_row[col.key]
        new = state.attrs[col.key].value

        if old == new:
            continue

        # Секретні значення приховуємо
        if _is_sensitive(col.key):
            old_text = _REDACTED
            new_text = _REDACTED

        else:
            old_text = _text(old)
            new_text = _text(new)

        _record(
            mapper,
            connection,
            target,
            action="update",
            field_name=col.key,
            old_value=old_text,
            new_value=new_text,
        )


# Автоматичне журналювання видалення
def _after_delete(mapper: Mapper, connection, target: object) -> None:

    _record(mapper, connection, target, action="delete")


# Увімкнення аудиту для SQLAlchemy
def enable_audit() -> None:

    global _ENABLED

    # Не реєструємо події повторно
    if _ENABLED:
        return

    event.listen(Mapper, "after_insert", _after_insert)

    event.listen(Mapper, "before_update", _before_update)

    event.listen(Mapper, "after_delete", _after_delete)

    _ENABLED = True
