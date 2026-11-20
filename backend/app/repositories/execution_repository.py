"""Execution data access; all writes are owned by the service transaction."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.execution import Execution


class ExecutionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, measure_id: str, period: str, user_id: int, *, lock: bool = False) -> Execution | None:
        stmt = select(Execution).where(
            Execution.measure_id == measure_id,
            Execution.period == period,
            Execution.submitted_by_user_id == user_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def by_id(self, execution_id: int, *, lock: bool = False) -> Execution | None:
        stmt = select(Execution).where(Execution.id == execution_id)
        if lock:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def list(self, *, measure_ids: set[str], period: str | None = None,
             status: str | None = None, department_ids: set[str] | None = None,
             submitted_by: int | None = None,
             offset: int = 0, limit: int = 100) -> list[Execution]:
        if not measure_ids:
            return []
        stmt = select(Execution).where(Execution.measure_id.in_(measure_ids))
        if period is not None:
            stmt = stmt.where(Execution.period == period)
        if status is not None:
            stmt = stmt.where(Execution.status == status)
        if department_ids is not None:
            stmt = stmt.where(Execution.submitted_department_id.in_(department_ids))
        if submitted_by is not None:
            stmt = stmt.where(Execution.submitted_by_user_id == submitted_by)
        stmt = stmt.order_by(Execution.period.desc(), Execution.measure_id, Execution.submitted_by_user_id).offset(offset).limit(limit)
        return list(self.db.scalars(stmt))
