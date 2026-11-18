from datetime import datetime

from sqlalchemy.orm import Session

from app.models.action_log import ActionLog

from app.repositories.action_log_repository import ActionLogRepository


class ActionLogNotFoundError(Exception):
    pass


class ActionLogService:

    def __init__(self, db: Session):
        self.repo = ActionLogRepository(db)

    # Отримати одну подію
    def get_log(self, log_id: str) -> ActionLog:

        log = self.repo.get_by_id(log_id)

        if log is None:
            raise ActionLogNotFoundError("Запис аудиту не знайдено")

        return log

    # Отримати список подій
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

        return self.repo.list_logs(
            skip=skip,
            limit=limit,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            since=since,
            until=until,
        )
