"""Лише SQLAlchemy-запити. Авторизацію робить DashboardService через workflow."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.execution import Execution
from app.models.measure import Measure
from app.models.risk import Risk
from app.models.risk_measurement import RiskMeasurement


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def measures(self, program_id: str, visible_ids: set[str]) -> list[Measure]:
        if not visible_ids:
            return []
        stmt = (select(Measure)
                .where(Measure.program_id == program_id, Measure.id.in_(visible_ids))
                .order_by(Measure.section_id, Measure.sequence_number, Measure.id))
        return list(self.db.scalars(stmt))

    def executions(self, measure_ids: set[str], period: str) -> dict[str, Execution]:
        if not measure_ids:
            return {}
        stmt = select(Execution).where(
            Execution.measure_id.in_(measure_ids), Execution.period == period
        )
        return {row.measure_id: row for row in self.db.scalars(stmt)}

    def departments(self, department_ids: set[str]) -> dict[str, str]:
        if not department_ids:
            return {}
        stmt = select(Department.id, Department.name).where(Department.id.in_(department_ids))
        return dict(self.db.execute(stmt))

    def risks(
        self,
        program_id: str,
        *,
        allowed_risk_ids: set[str] | None,
        owned_department_ids: set[str] | None,
    ) -> list[Risk]:
        stmt = select(Risk).where(Risk.program_id == program_id)
        # MAIN_KOORD: обидва None => всі ризики власної програми.
        # KOORD: ризики видимих заходів + ризики підрозділів своєї гілки.
        # VYK: лише ризики персонально призначених заходів.
        if allowed_risk_ids is not None:
            from sqlalchemy import or_
            predicates = [Risk.id.in_(allowed_risk_ids)]
            if owned_department_ids is not None:
                predicates.append(Risk.owner_department_id.in_(owned_department_ids))
            stmt = stmt.where(or_(*predicates))
        return list(self.db.scalars(stmt.order_by(Risk.id)))

    def latest_measurements(self, risk_ids: set[str], as_of: date) -> dict[str, RiskMeasurement]:
        if not risk_ids:
            return {}
        stmt = (select(RiskMeasurement)
                .where(RiskMeasurement.risk_id.in_(risk_ids),
                       RiskMeasurement.measured_on <= as_of)
                .order_by(RiskMeasurement.risk_id, RiskMeasurement.measured_on.desc()))
        result: dict[str, RiskMeasurement] = {}
        for row in self.db.scalars(stmt):
            result.setdefault(row.risk_id, row)
        return result

    def risk_ids_covered_by_program(self, program_id: str) -> set[str]:
        """Враховує ВСІ заходи програми, не лише видимі KOORD/VYK."""
        stmt = select(Measure.risk_id).where(
            Measure.program_id == program_id, Measure.risk_id.is_not(None)
        )
        return set(self.db.scalars(stmt))
