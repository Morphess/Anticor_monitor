from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db

from app.repositories.action_log_feed_repository import ActionLogFeedRepository
from app.schemas.action_logs import (
    ActionLogActor,
    ActionLogFacets,
    ActionLogFeedItem,
    ActionLogFeedPage,
    ActionLogRead,
)

from app.services.action_log_services import (
    ActionLogNotFoundError,
    ActionLogService,
)


router = APIRouter(
    prefix="/action-logs",
    tags=["Action Logs"],
    dependencies=[Depends(require_admin)],
)


# READ — список подій
@router.get("/", response_model=list[ActionLogRead])
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

    # У базі час зберігається в UTC
    # без інформації про часовий пояс
    for field_name, value in (("since", since), ("until", until)):
        if value is not None and value.tzinfo is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{field_name} передавай у UTC " "без timezone, як у PostgreSQL"
                ),
            )

    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=422, detail="since має бути <= until")

    return ActionLogService(db).list_logs(
        skip=skip,
        limit=limit,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        since=since,
        until=until,
    )


def _check_utc_range(since: datetime | None, until: datetime | None) -> None:
    # У базі час зберігається в UTC без часового поясу.
    for field_name, value in (("since", since), ("until", until)):
        if value is not None and value.tzinfo is not None:
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} передавай у UTC без timezone, як у PostgreSQL",
            )
    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=422, detail="since має бути <= until")


# READ — журнал для кабінету адміністратора: сторінки, пошук, фільтри,
# хто (логін, посада, підрозділ) і коли. Маршрут оголошено ДО /{log_id}.
@router.get("/feed", response_model=ActionLogFeedPage, summary="Журнал дій: сторінки, пошук і фільтри")
def feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str | None = Query(None, max_length=100, description="Пошук: логін, посада, підрозділ, об'єкт, поле, значення"),
    actor_user_id: int | None = None,
    department_id: str | None = Query(None, max_length=10, description="Підрозділ користувача; «-» — без підрозділу"),
    action: str | None = Query(None, max_length=50),
    entity_type: str | None = Query(None, max_length=50),
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
):
    _check_utc_range(since, until)
    total, rows = ActionLogFeedRepository(db).page(
        page=page, page_size=page_size, q=(q or "").strip() or None,
        actor_user_id=actor_user_id, department_id=department_id,
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
            id=log.id, occurred_at=log.occurred_at, actor=actor, action=log.action,
            entity_type=log.entity_type, entity_id=log.entity_id, field_name=log.field_name,
            old_value=log.old_value, new_value=log.new_value,
        ))
    return ActionLogFeedPage(total=total, page=page, page_size=page_size, items=items)


@router.get("/facets", response_model=ActionLogFacets, summary="Значення для фільтрів журналу")
def facets(db: Session = Depends(get_db)):
    actions, entity_types = ActionLogFeedRepository(db).facets()
    return ActionLogFacets(actions=actions, entity_types=entity_types)


# READ — одна подія
@router.get("/{log_id}", response_model=ActionLogRead)
def get_log(log_id: str, db: Session = Depends(get_db)):

    try:
        return ActionLogService(db).get_log(log_id)

    except ActionLogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
