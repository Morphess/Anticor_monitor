from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deadline_change import DeadlineChange


class DeadlineChangeRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати рішення за ID
    def get_by_id(self, change_id: int) -> DeadlineChange | None:

        return self.db.get(DeadlineChange, change_id)

    # Отримати список рішень
    def list_changes(
        self, skip: int = 0, limit: int = 20, measure_id: str | None = None
    ) -> list[DeadlineChange]:

        stmt = select(DeadlineChange)

        if measure_id is not None:
            stmt = stmt.where(DeadlineChange.measure_id == measure_id)

        stmt = (
            stmt.order_by(DeadlineChange.decision_date.desc(), DeadlineChange.id.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())

    # Останнє рішення для заходу
    def get_latest(self, measure_id: str) -> DeadlineChange | None:

        stmt = (
            select(DeadlineChange)
            .where(DeadlineChange.measure_id == measure_id)
            .order_by(DeadlineChange.decision_date.desc(), DeadlineChange.id.desc())
            .limit(1)
        )

        return self.db.scalar(stmt)

    # Попереднє рішення перед поточним останнім
    def get_previous(self, measure_id: str) -> DeadlineChange | None:

        stmt = (
            select(DeadlineChange)
            .where(DeadlineChange.measure_id == measure_id)
            .order_by(DeadlineChange.decision_date.desc(), DeadlineChange.id.desc())
            .offset(1)
            .limit(1)
        )

        return self.db.scalar(stmt)

    # Зберегти рішення
    def save(self, change: DeadlineChange) -> DeadlineChange:

        self.db.add(change)
        self.db.commit()
        self.db.refresh(change)

        return change

    # Видалити рішення
    def delete(self, change: DeadlineChange) -> None:

        self.db.delete(change)
        self.db.commit()
