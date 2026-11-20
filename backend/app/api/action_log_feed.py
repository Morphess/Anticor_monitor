"""ДВА нові маршрути журналу (вставити в main.py перед старим /{log_id})."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db
from app.repositories.action_log_feed_repository import ActionLogFeedRepository
from app.schemas.action_log_feed import ActionLogActor, ActionLogFacets, ActionLogFeedItem, ActionLogFeedPage
from app.services.action_log_writer import audit_value

router = APIRouter(
    prefix="/action-logs", tags=["Action Logs"],
    dependencies=[Depends(require_admin)],
)


def _as_utc_naive(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_department(value: str | None) -> int | str | None:
    if value in (None, "", "-"):
        return value or None
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise HTTPException(422, detail="department_id має бути числовим або '-' ")
    if n < 1:
        raise HTTPException(422, detail="department_id має бути додатним")
    return n


@router.get("/feed", response_model=ActionLogFeedPage)
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
    since = _as_utc_naive(since)
    until = _as_utc_naive(until)
    if since is not None and until is not None and since > until:
        raise HTTPException(422, detail="since має бути <= until")
    total, rows = ActionLogFeedRepository(db).page(
        page=page, page_size=page_size, q=(q or "").strip() or None,
        actor_user_id=actor_user_id, department_id=_parse_department(department_id),
        action=action, entity_type=entity_type, since=since, until=until,
    )
    items = []
    for log, user, department in rows:
        actor = None
        if user is not None:
            actor = ActionLogActor(
                id=user.id, login=user.login, role_id=user.role_id, position=user.position,
                department_id=user.department_id,
                department_name=department.name if department is not None else None,
            )
        items.append(ActionLogFeedItem(
            id=log.id, occurred_at=log.occurred_at, actor=actor,
            action=log.action, entity_type=log.entity_type,
            entity_id=log.entity_id, field_name=log.field_name,
            # Маскування й для ІСТОРИЧНИХ рядків, записаних старим кодом.
            old_value=audit_value(log.field_name, log.old_value),
            new_value=audit_value(log.field_name, log.new_value),
        ))
    return ActionLogFeedPage(total=total, page=page, page_size=page_size, items=items)


@router.get("/facets", response_model=ActionLogFacets)
def facets(db: Session = Depends(get_db)):
    actions, entity_types = ActionLogFeedRepository(db).facets()
    return ActionLogFacets(actions=actions, entity_types=entity_types)
