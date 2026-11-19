"""Автоматичні внутрішні нагадування про контрольні строки (D7 / D3).

Обчислюються в момент запиту, без cron, без змін у таблицях та без
спотворення правил RF1. Видимість із measure_access (workflow та assignments).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.repositories.deadline_reminder_repository import DeadlineReminderRepository
from app.schemas.deadline_reminders import DeadlineReminderItem, DeadlineRemindersRead
from app.services.measure_access import visible_measure_ids
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError


class DeadlineReminderError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class DeadlineReminderService:
    ALLOWED_ROLES = frozenset({"MAIN_KOORD", "KOORD", "VYK"})

    def __init__(self, db: Session):
        self.db = db
        self.repo = DeadlineReminderRepository(db)

    def get_reminders(
        self,
        actor,
        *,
        as_of: date,
        program_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> DeadlineRemindersRead:
        if actor.role_id not in self.ALLOWED_ROLES:
            raise DeadlineReminderError("Немає доступу до нагадувань", 403)
        if offset < 0 or not (1 <= limit <= 500):
            raise DeadlineReminderError("Некоректні параметри пагінації", 422)

        if program_id is not None:
            # На відміну від простого фільтра, чужа програма поверне 403.
            try:
                ProgramWorkflowService(self.db).visible_program(program_id, actor)
            except WorkflowError as exc:
                raise DeadlineReminderError(exc.detail, exc.status_code) from exc

        visible_ids = visible_measure_ids(self.db, actor, program_id=program_id)
        candidates = self.repo.candidates(
            visible_ids, as_of=as_of, program_id=program_id
        )
        approved = self.repo.approved_completed_ids({m.id for m in candidates})
        reminders: list[DeadlineReminderItem] = []

        for measure in candidates:
            if measure.id in approved:
                continue
            days = (measure.deadline_on - as_of).days
            if not 1 <= days <= 7:
                continue
            urgent = days <= 3
            code = "D3" if urgent else "D7"
            reminders.append(
                DeadlineReminderItem(
                    id=f"{code}:{measure.id}:{measure.deadline_on.isoformat()}",
                    code=code,
                    level="urgent" if urgent else "warning",
                    program_id=measure.program_id,
                    measure_id=measure.id,
                    description=measure.description,
                    responsible_department_id=measure.responsible_department_id,
                    deadline_on=measure.deadline_on,
                    days_left=days,
                    message=(
                        f"До строку виконання заходу {measure.id} залишилося "
                        f"{days} дн. (до {measure.deadline_on.isoformat()})."
                    ),
                )
            )

        reminders.sort(key=lambda r: (r.days_left, r.deadline_on, r.measure_id))
        return DeadlineRemindersRead(
            as_of=as_of,
            total=len(reminders),
            warning=sum(r.code == "D7" for r in reminders),
            urgent=sum(r.code == "D3" for r in reminders),
            offset=offset,
            limit=limit,
            reminders=reminders[offset : offset + limit],
        )
