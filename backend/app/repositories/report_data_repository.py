"""Читання вихідних даних звіту, без авторизації та бізнес-логіки."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.execution import Execution
from app.models.measure import Measure
from app.models.order_version import OrderVersion
from app.models.program import Program
from app.models.section import Section
from app.services.execution_summary import summaries, assignments_for


class ReportDataRepository:
    def __init__(self, db: Session):
        self.db = db

    def program(self, program_id: str) -> Program | None:
        return self.db.get(Program, program_id)

    def sections(self) -> list[Section]:
        return list(self.db.scalars(select(Section).order_by(Section.number, Section.id)))

    def measures(self, ids: set[str]) -> list[Measure]:
        if not ids:
            return []
        return list(self.db.scalars(select(Measure).where(Measure.id.in_(ids))))

    def executions(self, ids: set[str], period: str) -> dict:
        if not ids:
            return {}
        rows = list(self.db.scalars(select(Execution).where(
            Execution.measure_id.in_(ids), Execution.period == period
        )))
        return summaries(self.db, ids, period, rows)

    def evidence_counts(self, ids: set[str], period: str) -> dict[str, int]:
        """Legacy schema field: count linked order documents, NOT removed Evidence rows.

        Count approved, pinned documents belonging to currently assigned executors.
        One measure may have several documents (one for each executor).
        Byte-level integrity is separately checked before approval and by the scanner.
        """
        if not ids:
            return {}
        active = assignments_for(self.db, ids)
        # Count exact current assignments, not old/revoked executor submissions.
        matched = list(self.db.scalars(select(Execution).where(
            Execution.measure_id.in_(ids), Execution.period == period,
            Execution.status == "approved", Execution.document_changed.is_(False),
            Execution.order_version_id.is_not(None),
        )))
        return {mid: sum(1 for row in matched if row.measure_id == mid
                         and row.submitted_by_user_id in active.get(mid, set())
                         and (version := self.db.get(OrderVersion, row.order_version_id)) is not None
                         and version.order_id == row.order_id and version.sha256 == row.submitted_sha256)
                for mid in ids}

    def departments(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        stmt = select(Department.id, Department.name).where(Department.id.in_(ids))
        return {department_id: name for department_id, name in self.db.execute(stmt)}
