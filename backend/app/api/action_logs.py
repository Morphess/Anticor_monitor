from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db

from app.schemas.action_logs import ActionLogRead

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


# READ — одна подія
@router.get("/{log_id}", response_model=ActionLogRead)
def get_log(log_id: str, db: Session = Depends(get_db)):

    try:
        return ActionLogService(db).get_log(log_id)

    except ActionLogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
