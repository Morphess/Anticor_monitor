from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog


class ActionLogRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати запис за ID
    def get_by_id(self, log_id: str) -> ActionLog | None:

        return self.db.get(ActionLog, log_id)

    # Отримати список подій аудиту
    def list_logs(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        actor_user_id: int | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ActionLog]:

        stmt = select(ActionLog)

        # Фільтр за користувачем
        if actor_user_id is not None:
            stmt = stmt.where(ActionLog.actor_user_id == actor_user_id)

        # Фільтр за дією
        if action is not None:
            stmt = stmt.where(ActionLog.action == action)

        # Фільтр за таблицею
        if entity_type is not None:
            stmt = stmt.where(ActionLog.entity_type == entity_type)

        # Фільтр за ID об'єкта
        if entity_id is not None:
            stmt = stmt.where(ActionLog.entity_id == entity_id)

        # Фільтр за початковою датою
        if since is not None:
            stmt = stmt.where(ActionLog.occurred_at >= since)

        # Фільтр за кінцевою датою
        if until is not None:
            stmt = stmt.where(ActionLog.occurred_at <= until)

        stmt = stmt.order_by(ActionLog.occurred_at.desc(), ActionLog.id.desc())

        return list(self.db.scalars(stmt.offset(skip).limit(limit)).all())
