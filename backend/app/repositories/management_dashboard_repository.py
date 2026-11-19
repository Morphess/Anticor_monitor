"""Read-only SQLAlchemy queries; never decides user permissions on its own."""
from __future__ import annotations

from datetime import date

from sqlalchemy import MetaData, Table, inspect, or_, select
from sqlalchemy.orm import Session

from app.models.deadline_change import DeadlineChange
from app.models.department import Department
from app.models.evidence import Evidence
from app.models.execution import Execution
from app.models.measure import Measure, MeasureCollaborator
from app.models.program import Program
from app.models.program_workflow import MeasureAssignment, ProgramDepartment
from app.models.section import Section
from app.models.risk import Risk
from app.models.risk_measurement import RiskMeasurement


class ManagementDashboardRepository:
    def __init__(self, db: Session):
        self.db = db

    def all_program_ids(self) -> set[str]:
        """Усі створені програми — лише для керівника відомства."""
        return set(self.db.scalars(select(Program.id)))

    def program_rows(self, ids: set[str]) -> list[Program]:
        if not ids:
            return []
        return list(self.db.scalars(select(Program).where(Program.id.in_(ids)).order_by(Program.id)))

    def program_dispatch_rows(self, program_ids: set[str]) -> list[tuple]:
        if not program_ids:
            return []
        return list(self.db.execute(
            select(ProgramDepartment.program_id, ProgramDepartment.department_id, ProgramDepartment.sent_at)
            .where(ProgramDepartment.program_id.in_(program_ids))
            .order_by(ProgramDepartment.sent_at)
        ).all())

    def sections(self, ids: set[str]) -> dict[str, Section]:
        if not ids:
            return {}
        return {s.id: s for s in self.db.scalars(select(Section).where(Section.id.in_(ids)))}

    def assigned_units(self, measure_ids: set[str]) -> dict[str, set[str]]:
        """measure -> відділи, яким доручено захід (без користувачів)."""
        if not measure_ids:
            return {}
        result: dict[str, set[str]] = {}
        rows = self.db.execute(
            select(MeasureAssignment.measure_id, MeasureAssignment.department_id)
            .where(MeasureAssignment.measure_id.in_(measure_ids)).distinct()
        )
        for measure_id, department_id in rows:
            result.setdefault(measure_id, set()).add(department_id)
        return result

    def dispatches(self, department_ids: set[str]) -> dict[str, set[str]]:
        """program -> departments that explicitly received it (including ancestors)."""
        if not department_ids:
            return {}
        result: dict[str, set[str]] = {}
        rows = self.db.execute(
            select(ProgramDepartment.program_id, ProgramDepartment.department_id)
            .where(ProgramDepartment.department_id.in_(department_ids))
        )
        for program_id, department_id in rows:
            result.setdefault(program_id, set()).add(department_id)
        return result

    def programs(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        return dict(self.db.execute(select(Program.id, Program.title).where(Program.id.in_(ids))).all())

    def departments(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        return dict(self.db.execute(select(Department.id, Department.name).where(Department.id.in_(ids))).all())

    def measures(self, program_ids: set[str], branch: set[str]) -> list[Measure]:
        if not program_ids or not branch:
            return []
        # Both responsible and collaborating departments count; DISTINCT avoids duplication.
        stmt = (
            select(Measure)
            .outerjoin(MeasureCollaborator, MeasureCollaborator.measure_id == Measure.id)
            .where(
                Measure.program_id.in_(program_ids),
                or_(Measure.responsible_department_id.in_(branch),
                    MeasureCollaborator.department_id.in_(branch),
                    Measure.id.in_(select(MeasureAssignment.measure_id)
                                   .where(MeasureAssignment.department_id.in_(branch)))),
            )
            .distinct()
            .order_by(Measure.program_id, Measure.section_id,
                      Measure.sequence_number, Measure.id)
        )
        return list(self.db.scalars(stmt))

    def collaborators(self, ids: set[str]) -> dict[str, set[str]]:
        if not ids:
            return {}
        rows = self.db.execute(
            select(MeasureCollaborator.measure_id, MeasureCollaborator.department_id)
            .where(MeasureCollaborator.measure_id.in_(ids))
        )
        result: dict[str, set[str]] = {}
        for measure_id, dept_id in rows:
            result.setdefault(measure_id, set()).add(dept_id)
        return result

    def executions(self, ids: set[str], period: str) -> dict[str, Execution]:
        if not ids:
            return {}
        stmt = select(Execution).where(Execution.measure_id.in_(ids), Execution.period == period)
        return {r.measure_id: r for r in self.db.scalars(stmt)}

    def evidences(self, ids: set[str], as_of: date) -> list[Evidence]:
        if not ids:
            return []
        return list(self.db.scalars(select(Evidence).where(Evidence.measure_id.in_(ids))))

    def deadline_changes(self, ids: set[str], as_of: date) -> list[DeadlineChange]:
        if not ids:
            return []
        return list(self.db.scalars(select(DeadlineChange).where(
            DeadlineChange.measure_id.in_(ids), DeadlineChange.decision_date <= as_of
        )))

    def risks(self, program_ids: set[str], branch: set[str], linked: set[str]) -> list[Risk]:
        if not program_ids:
            return []
        stmt = select(Risk).where(
            Risk.program_id.in_(program_ids),
            or_(Risk.owner_department_id.in_(branch), Risk.id.in_(linked)),
        ).order_by(Risk.program_id, Risk.id)
        return list(self.db.scalars(stmt))

    def all_covered_risks(self, program_ids: set[str]) -> set[str]:
        """Global existence check only; does not reveal foreign measures."""
        if not program_ids:
            return set()
        stmt = select(Measure.risk_id).where(
            Measure.program_id.in_(program_ids), Measure.risk_id.is_not(None)
        )
        return set(self.db.scalars(stmt))

    def measurements(self, ids: set[str], as_of: date) -> list[RiskMeasurement]:
        if not ids:
            return []
        return list(self.db.scalars(
            select(RiskMeasurement).where(
                RiskMeasurement.risk_id.in_(ids),
                RiskMeasurement.measured_on <= as_of,
            ).order_by(RiskMeasurement.risk_id, RiskMeasurement.measured_on.desc())
        ))

    def optional_event_rows(self, table_name: str, measure_ids: set[str]) -> list[dict]:
        """Use optional RF8/order-version tables only if their migrations are installed.

        Fixed allow-list: never accept SQL table names from request parameters.
        """
        if not measure_ids or table_name not in {"invalid_order_references", "order_change_alerts"}:
            return []
        bind = self.db.get_bind()
        if not inspect(bind).has_table(table_name):
            return []
        tbl = Table(table_name, MetaData(), autoload_with=bind)
        stmt = select(tbl).where(tbl.c.measure_id.in_(measure_ids))
        return [dict(row) for row in self.db.execute(stmt).mappings().all()]
