"""Доступ до таблиці executions через SQLAlchemy 2.x."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution import Execution


class ExecutionRepository:
    def get(self, db: Session, measure_id: str, period: str) -> Execution | None:
        # Ключ складений: (measure_id, period).
        return db.get(Execution, (measure_id, period))

    def list(
        self,
        db: Session,
        *,
        measure_id: str | None = None,
        period: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Execution]:
        stmt = select(Execution)
        if measure_id is not None:
            stmt = stmt.where(Execution.measure_id == measure_id)
        if period is not None:
            stmt = stmt.where(Execution.period == period)
        if status is not None:
            stmt = stmt.where(Execution.status == status)
        stmt = stmt.order_by(Execution.period.desc(), Execution.measure_id.asc())
        stmt = stmt.offset(offset).limit(limit)
        return list(db.scalars(stmt).all())

    def add(self, db: Session, execution: Execution) -> None:
        db.add(execution)

    def update(self, execution: Execution, changes: dict[str, Any]) -> None:
        for field_name, value in changes.items():
            setattr(execution, field_name, value)

    def set_approval(
        self,
        execution: Execution,
        approved: bool,
    ) -> None:
        """Зміна погодження звіту координатором."""

        execution.approved_by_coordinator = approved

    def delete(self, db: Session, execution: Execution) -> None:
        db.delete(execution)
