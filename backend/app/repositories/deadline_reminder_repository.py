"""SQLAlchemy-запити для нагадувань: без записів до БД."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deadline_change import DeadlineChange
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
    ) -> list[tuple[Measure, date]]:
        """Доступні заходи, чинний строк яких настає в наступні 1–7 днів.

        Чинний строк — новий строк з останнього рішення про перенесення,
        ухваленого не пізніше as_of; якщо перенесень не було — первинний
        Measure.deadline_on. Повертає пари (захід, чинний строк).
        """
        if not visible_ids:
            return []

        ranked = (
            select(
                DeadlineChange.measure_id.label("measure_id"),
                DeadlineChange.new_deadline.label("new_deadline"),
                func.row_number().over(
                    partition_by=DeadlineChange.measure_id,
                    order_by=(DeadlineChange.decision_date.desc(), DeadlineChange.id.desc()),
                ).label("rn"),
            )
            .where(
                DeadlineChange.measure_id.in_(visible_ids),
                DeadlineChange.decision_date <= as_of,
            )
            .subquery()
        )
        latest = select(ranked.c.measure_id, ranked.c.new_deadline).where(ranked.c.rn == 1).subquery()
        effective = func.coalesce(latest.c.new_deadline, Measure.deadline_on).label("effective_deadline")

        stmt = (
            select(Measure, effective)
            .outerjoin(latest, latest.c.measure_id == Measure.id)
            .where(
                Measure.id.in_(visible_ids),
                Measure.deadline_type == "date",
                effective.between(as_of + timedelta(days=1), as_of + timedelta(days=7)),
            )
        )
        if program_id is not None:
            stmt = stmt.where(Measure.program_id == program_id)
        stmt = stmt.order_by(effective, Measure.id)
        return [(measure, deadline) for measure, deadline in self.db.execute(stmt)]

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
