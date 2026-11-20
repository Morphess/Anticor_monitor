"""API журналу дій для Anticor Monitor.

ВАЖЛИВО: конкретні /feed і /facets оголошені ПЕРЕД /{log_id}.
Використовує наявну модель ActionLog і сервіс ActionLogService.
Готовий до заміни backend/app/api/action_logs.py (без зміни main.py, якщо
router цього модуля вже підключений з prefix='/api').
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db
from app.models.action_log import ActionLog
from app.models.department import Department
from app.models.user import User
from app.services.action_log_services import ActionLogNotFoundError, ActionLogService


router = APIRouter(
    prefix="/action-logs",
    tags=["Action Logs"],
    dependencies=[Depends(require_admin)],
)


class ActionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    occurred_at: datetime
    actor_user_id: int | None
    action: str
    entity_type: str
    entity_id: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class ActionLogActor(BaseModel):
    id: int
    login: str
    role_id: str
    position: str | None = None
    # Коди підрозділів у базі можуть бути текстовими, наприклад "P01".
    department_id: str | None = None
    department_name: str | None = None


class ActionLogFeedItem(BaseModel):
    id: str
    occurred_at: datetime
    actor: ActionLogActor | None = None
    action: str
    entity_type: str
    entity_id: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class ActionLogFeedPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ActionLogFeedItem]


class ActionLogFacets(BaseModel):
    actions: list[str]
    entity_types: list[str]


# Навіть якщо в історичних записах трапляються секрети, не видаємо їх API.
_SENSITIVE_FIELD = re.compile(
    r"password|passwd|passphrase|secret|token|authorization|credential|private.?key|"
    r"api.?key|session.?key|cookie|refresh.?key|access.?key",
    re.IGNORECASE,
)


def _safe_value(field_name: str | None, value: str | None) -> str | None:
    if value is None:
        return None
    if _SENSITIVE_FIELD.search(field_name or ""):
        return "[REDACTED]"
    return value


def _utc_naive(value: datetime | None) -> datetime | None:
    """Час у action_logs.occurred_at зберігається як naive UTC."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _date_range(
    since: datetime | None,
    until: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    since, until = _utc_naive(since), _utc_naive(until)
    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=422, detail="since має бути <= until")
    return since, until


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _department_filter(value: str | None) -> str | None:
    """Підтримка кодів підрозділів на кшталт P01 і числових ID."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _public_old(log: ActionLog) -> ActionLogRead:
    return ActionLogRead(
        id=str(log.id),
        occurred_at=log.occurred_at,
        actor_user_id=log.actor_user_id,
        action=log.action,
        entity_type=log.entity_type,
        entity_id=str(log.entity_id),
        field_name=log.field_name,
        old_value=_safe_value(log.field_name, log.old_value),
        new_value=_safe_value(log.field_name, log.new_value),
    )


# 1. /feed ПОВИНЕН стояти раніше /{log_id}.
@router.get(
    "/feed", response_model=ActionLogFeedPage, summary="Журнал дій: пошук і сторінки"
)
def feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str | None = Query(None, max_length=100),
    actor_user_id: int | None = Query(None, ge=1),
    department_id: str | None = Query(None, max_length=20),
    action: str | None = Query(None, max_length=50),
    entity_type: str | None = Query(None, max_length=50),
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    since, until = _date_range(since, until)
    dept = _department_filter(department_id)

    stmt = (
        select(ActionLog, User, Department)
        .outerjoin(User, User.id == ActionLog.actor_user_id)
        .outerjoin(Department, Department.id == User.department_id)
    )
    if actor_user_id is not None:
        stmt = stmt.where(ActionLog.actor_user_id == actor_user_id)
    if dept == "-":
        stmt = stmt.where(User.department_id.is_(None))
    elif dept is not None:
        stmt = stmt.where(cast(User.department_id, String) == dept)
    if action:
        stmt = stmt.where(ActionLog.action == action)
    if entity_type:
        stmt = stmt.where(ActionLog.entity_type == entity_type)
    if since:
        stmt = stmt.where(ActionLog.occurred_at >= since)
    if until:
        stmt = stmt.where(ActionLog.occurred_at <= until)

    # Пошук у відкритих даних, не індексуємо чутливі значення змін.
    for word in (q or "").split():
        pattern = _like_pattern(word)
        stmt = stmt.where(
            or_(
                ActionLog.action.ilike(pattern, escape="\\"),
                ActionLog.entity_type.ilike(pattern, escape="\\"),
                ActionLog.entity_id.ilike(pattern, escape="\\"),
                ActionLog.field_name.ilike(pattern, escape="\\"),
                User.login.ilike(pattern, escape="\\"),
                User.position.ilike(pattern, escape="\\"),
                Department.name.ilike(pattern, escape="\\"),
                cast(User.department_id, String).ilike(pattern, escape="\\"),
                cast(ActionLog.actor_user_id, String).ilike(pattern, escape="\\"),
            )
        )

    total = (
        db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    )
    rows = db.execute(
        stmt.order_by(ActionLog.occurred_at.desc(), ActionLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for log, user, department in rows:
        actor = None
        if user is not None:
            actor = ActionLogActor(
                id=user.id,
                login=user.login,
                role_id=user.role_id,
                position=user.position,
                department_id=(
                    str(user.department_id) if user.department_id is not None else None
                ),
                department_name=department.name if department is not None else None,
            )
        items.append(
            ActionLogFeedItem(
                id=str(log.id),
                occurred_at=log.occurred_at,
                actor=actor,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=str(log.entity_id),
                field_name=log.field_name,
                old_value=_safe_value(log.field_name, log.old_value),
                new_value=_safe_value(log.field_name, log.new_value),
            )
        )
    return ActionLogFeedPage(total=total, page=page, page_size=page_size, items=items)


# 2. /facets теж ПОВИНЕН стояти раніше /{log_id}.
@router.get("/facets", response_model=ActionLogFacets, summary="Фільтри журналу")
def facets(db: Session = Depends(get_db)):
    return ActionLogFacets(
        actions=list(
            db.scalars(select(ActionLog.action).distinct().order_by(ActionLog.action))
        ),
        entity_types=list(
            db.scalars(
                select(ActionLog.entity_type).distinct().order_by(ActionLog.entity_type)
            )
        ),
    )


# 3. Зберігаємо сумісність зі старим GET /api/action-logs/.
@router.get("/", response_model=list[ActionLogRead], summary="Старий список записів")
def list_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    actor_user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    since, until = _date_range(since, until)
    logs = ActionLogService(db).list_logs(
        skip=skip,
        limit=limit,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        since=since,
        until=until,
    )
    return [_public_old(log) for log in logs]


# 4. Найзагальніший маршрут — завжди внизу файлу.
@router.get("/{log_id}", response_model=ActionLogRead, summary="Один запис журналу")
def get_log(log_id: str, db: Session = Depends(get_db)):
    try:
        log = ActionLogService(db).get_log(log_id)
    except ActionLogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _public_old(log)
