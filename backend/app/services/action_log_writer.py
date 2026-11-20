"""Запис подій аудиту в тій самій транзакції, що й бізнес-операція.

Не робить commit: викликати ДО db.commit() в існуючому сервісі.
Не викликати для переглядів (GET) та не журналювати секрети/довільні JSON payload.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session
from app.models.action_log import ActionLog

REDACTED = "[REDACTED]"
MAX_VALUE_LENGTH = 4000
SENSITIVE_PARTS = (
    "password", "passwd", "secret", "token", "credential", "authorization",
    "api_key", "private_key", "cookie", "session_key", "refresh_key",
)


def is_sensitive_field(field_name: str | None) -> bool:
    name = (field_name or "").lower()
    return bool(name) and any(part in name for part in SENSITIVE_PARTS)


def audit_value(field_name: str | None, value: object | None) -> str | None:
    """Нормалізує скаляр; небезпечні поля маскує ще до запису в БД."""
    if value is None:
        return None
    if is_sensitive_field(field_name):
        return REDACTED
    if isinstance(value, (dict, list, tuple, set, bytes, bytearray)):
        raise ValueError("У журнал можна писати лише скалярні значення, не payload/файли")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:MAX_VALUE_LENGTH]


def record_action(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | str,
    field_name: str | None = None,
    old_value: object | None = None,
    new_value: object | None = None,
) -> ActionLog:
    """Ставить дію в поточну транзакцію; actor_user_id брати лише з JWT-користувача."""
    if not action.strip() or not entity_type.strip() or not str(entity_id).strip():
        raise ValueError("action, entity_type та entity_id є обов'язковими")
    log = ActionLog(
        id=str(uuid4()),
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
        actor_user_id=actor_user_id,
        action=action.strip(),
        entity_type=entity_type.strip(),
        entity_id=str(entity_id),
        field_name=field_name,
        old_value=audit_value(field_name, old_value),
        new_value=audit_value(field_name, new_value),
    )
    db.add(log)
    return log


def record_changes(
    db: Session,
    *,
    actor_user_id: int | None,
    entity_type: str,
    entity_id: int | str,
    before: dict[str, object],
    after: dict[str, object],
) -> int:
    """Для UPDATE: записує одну подію на кожне змінене поле, не підмінюючи commit."""
    written = 0
    for field in after:
        if field not in before:
            continue
        if before[field] != after[field]:
            record_action(
                db, actor_user_id=actor_user_id, action="update",
                entity_type=entity_type, entity_id=entity_id, field_name=field,
                old_value=before[field], new_value=after[field],
            )
            written += 1
    return written


def public_action_log(log: ActionLog) -> dict:
    """Безпечна форма і для старих GET /action-logs/ та /{log_id}.

    Викликати в існуючих read-endpoints перед поверненням ActionLogRead.
    """
    return {
        "id": log.id,
        "occurred_at": log.occurred_at,
        "actor_user_id": log.actor_user_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "field_name": log.field_name,
        "old_value": audit_value(log.field_name, log.old_value),
        "new_value": audit_value(log.field_name, log.new_value),
    }
