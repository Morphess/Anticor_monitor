"""Читання вихідних даних звіту, без авторизації та бізнес-логіки."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.evidence import Evidence
from app.models.execution import Execution
from app.models.measure import Measure
from app.models.program import Program
from app.models.section import Section


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

    def executions(self, ids: set[str], period: str) -> dict[str, Execution]:
        if not ids:
            return {}
        rows = self.db.scalars(
            select(Execution).where(
                Execution.measure_id.in_(ids), Execution.period == period
            )
        )
        return {row.measure_id: row for row in rows}

    def evidence_counts(self, ids: set[str]) -> dict[str, int]:
        if not ids:
            return {}
        stmt = (
            select(Evidence.measure_id, func.count(Evidence.id))
            .where(Evidence.measure_id.in_(ids))
            .group_by(Evidence.measure_id)
        )
        return {measure_id: count for measure_id, count in self.db.execute(stmt)}

    def departments(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        stmt = select(Department.id, Department.name).where(Department.id.in_(ids))
        return {department_id: name for department_id, name in self.db.execute(stmt)}
