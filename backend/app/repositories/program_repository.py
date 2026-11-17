from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.program import Program


class ProgramRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати програму за її кодом.
    def get_by_id(self, program_id: str) -> Program | None:
        return self.db.get(Program, program_id)

    # Отримати список програм з пагінацією.
    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Program]:

        stmt = (
            select(Program)
            .order_by(Program.start_date.desc(), Program.id)
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())

    # Додати нову програму до транзакції.
    def create(self, program: Program) -> Program:
        self.db.add(program)
        self.db.flush()
        return program

    # Зберегти зміни програми в транзакції.
    def update(self, program: Program) -> Program:
        self.db.flush()
        return program

    # Видалити програму в межах транзакції.
    def delete(self, program: Program) -> None:
        self.db.delete(program)
        self.db.flush()
