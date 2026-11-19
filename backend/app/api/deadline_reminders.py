"""Персоналізований API внутрішніх нагадувань за 7 та 3 дні до строку."""

from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.deadline_reminders import DeadlineRemindersRead
from app.services.deadline_reminder_services import (
    DeadlineReminderError,
    DeadlineReminderService,
)
from app.services.measure_access import require_execution_actor


router = APIRouter(prefix="/deadline-reminders", tags=["Deadline Reminders"])


def _local_today() -> date:
    """Не використовуємо UTC-дату сервера для українських підрозділів."""
    try:
        zone = ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Kyiv"))
    except ZoneInfoNotFoundError:
        # На Windows без пакета tzdata використовуємо локальну дату ОС.
        # Для правильного часового поясу встанови: pip install tzdata
        return date.today()
    return datetime.now(zone).date()


@router.get(
    "/",
    response_model=DeadlineRemindersRead,
    summary="Мої нагадування за 7 і 3 дні до строків",
    description=(
        "D7 показується за 7–4 дні; D3 — за 3–1 день до строку. "
        "Нагадування зникає після погодженого completed. "
        "VYK бачить призначені заходи, KOORD — доступну гілку, "
        "MAIN_KOORD — власні програми. Це внутрішні нагадування при відкритті "
        "кабінету, а не фонові push/email повідомлення."
    ),
)
def list_deadline_reminders(
    program_id: str | None = Query(default=None, min_length=1),
    as_of: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
) -> DeadlineRemindersRead:
    try:
        return DeadlineReminderService(db).get_reminders(
            actor,
            as_of=as_of or _local_today(),
            program_id=program_id,
            offset=offset,
            limit=limit,
        )
    except DeadlineReminderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
