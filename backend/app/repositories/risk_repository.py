from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk import Risk


class RiskRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати ризик за ID
    def get_by_id(self, risk_id: str) -> Risk | None:
        return self.db.get(Risk, risk_id)

    # Отримати список ризиків
    def list_risks(
        self,
        skip: int = 0,
        limit: int = 20,
        program_id: str | None = None,
        owner_department_id: str | None = None,
    ) -> list[Risk]:

        stmt = select(Risk)

        # Фільтрація за програмою
        if program_id is not None:
            stmt = stmt.where(Risk.program_id == program_id)

        # Фільтрація за підрозділом
        if owner_department_id is not None:
            stmt = stmt.where(Risk.owner_department_id == owner_department_id)

        stmt = stmt.order_by(Risk.id).offset(skip).limit(limit)

        return list(self.db.scalars(stmt).all())

    # Створити або оновити ризик
    def save(self, risk: Risk) -> Risk:

        self.db.add(risk)
        self.db.commit()
        self.db.refresh(risk)

        return risk

    # Видалити ризик
    def delete(self, risk: Risk) -> None:

        self.db.delete(risk)
        self.db.commit()
