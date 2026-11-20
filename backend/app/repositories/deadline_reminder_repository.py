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
        """Suppress reminders only when *every current assignee* has approved."""
        if not measure_ids:
            return set()
        from app.services.execution_summary import summaries
        rows = list(self.db.scalars(select(Execution).where(
            Execution.measure_id.in_(measure_ids)
        )))
        approved = set()
        for period in {row.period for row in rows}:
            grouped = summaries(self.db, measure_ids, period,
                                [row for row in rows if row.period == period])
            approved.update(mid for mid, record in grouped.items()
                            if record.status == 'approved' and record.outcome_status == 'completed')
        return approved
