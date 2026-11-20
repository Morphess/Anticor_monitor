"""Читання вихідних даних звіту, без авторизації та бізнес-логіки."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.execution import Execution
from app.models.measure import Measure
from app.models.order_version import OrderVersion
from app.models.program import Program
from app.models.program_workflow import MeasureAssignment
from app.models.user import User
from app.models.section import Section
from app.services.execution_summary import summary_for


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

    def _active_users(self, ids: set[str], allowed_users: dict[str, set[int]] | None):
        if not ids:
            return {}
        assigned = defaultdict(set)
        # Only live VYK personnel actually in the assignment's department.
        for mid, user_id in self.db.execute(
            select(MeasureAssignment.measure_id, MeasureAssignment.user_id)
            .join(User, User.id == MeasureAssignment.user_id)
            .where(MeasureAssignment.measure_id.in_(ids),
                   User.department_id == MeasureAssignment.department_id,
                   User.role_id == "VYK")
        ):
            assigned[mid].add(user_id)
        if allowed_users is None:
            return dict(assigned)
        # Narrow to current actual assignments, never merely requested user ids.
        return {mid: assigned.get(mid, set()) & allowed_users.get(mid, set()) for mid in ids}

    def _valid_approval(self, row: Execution) -> bool:
        if row.status != "approved" or row.document_changed or not row.order_version_id:
            return False
        version = self.db.get(OrderVersion, row.order_version_id)
        return bool(version and version.order_id == row.order_id
                    and version.sha256 == row.submitted_sha256)

    def executions(
        self, ids: set[str], period: str,
        allowed_users: dict[str, set[int]] | None = None,
    ) -> dict:
        if not ids:
            return {}
        active = self._active_users(ids, allowed_users)
        rows = self.db.scalars(select(Execution).where(
            Execution.measure_id.in_(ids), Execution.period == period,
        )).all()
        grouped = defaultdict(list)
        for row in rows:
            if row.submitted_by_user_id not in active.get(row.measure_id, set()):
                continue
            # An invalid approved order must not be counted as approved.
            if row.status == "approved" and not self._valid_approval(row):
                continue
            grouped[row.measure_id].append(row)
        result = {}
        for mid in ids:
            item = summary_for(mid, period, grouped[mid], active.get(mid, set()))
            if item is not None:
                result[mid] = item
        return result

    def evidence_counts(
        self, ids: set[str], period: str,
        allowed_users: dict[str, set[int]] | None = None,
    ) -> dict[str, int]:
        if not ids:
            return {}
        active = self._active_users(ids, allowed_users)
        rows = self.db.scalars(select(Execution).where(
            Execution.measure_id.in_(ids), Execution.period == period,
            Execution.status == "approved", Execution.document_changed.is_(False),
            Execution.order_version_id.is_not(None),
        )).all()
        counts = defaultdict(int)
        for row in rows:
            if row.submitted_by_user_id in active.get(row.measure_id, set()) and self._valid_approval(row):
                counts[row.measure_id] += 1
        return dict(counts)

    def departments(self, ids: set[str]) -> dict[str, str]:
        if not ids:
            return {}
        stmt = select(Department.id, Department.name).where(Department.id.in_(ids))
        return {department_id: name for department_id, name in self.db.execute(stmt)}
