"""SQLAlchemy-запити для нагадувань: без записів до БД."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution import Execution
from app.models.measure import Measure


class DeadlineReminderRepository:
    def __init__(self, db: Session):
        self.db = db

    def candidates(
        self,
        visible_ids: set[str],
        *,
        as_of: date,
        program_id: str | None,
    ) -> list[Measure]:
        """Лише доступні заходи з фіксованим строком у наступні 1–7 днів."""
        if not visible_ids:
            return []

        stmt = select(Measure).where(
            Measure.id.in_(visible_ids),
            Measure.deadline_type == "date",
            Measure.deadline_on.between(
                as_of + timedelta(days=1),
                as_of + timedelta(days=7),
            ),
        )
        if program_id is not None:
            stmt = stmt.where(Measure.program_id == program_id)
        stmt = stmt.order_by(Measure.deadline_on, Measure.id)
        return list(self.db.scalars(stmt))

    def approved_completed_ids(self, measure_ids: set[str]) -> set[str]:
        """Разові заходи з погодженим 'completed' не потребують нагадувань.

        Перевіряємо всі періоди: для заходу deadline_type='date' встановлено
        один термін, і вже погоджене завершення не треба нагадувати повторно.
        """
        if not measure_ids:
            return set()
        stmt = (
            select(Execution.measure_id)
            .where(
                Execution.measure_id.in_(measure_ids),
                Execution.status == "completed",
                Execution.approved_by_coordinator.is_(True),
            )
            .distinct()
        )
        return set(self.db.scalars(stmt))
