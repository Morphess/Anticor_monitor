from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.section import Section


class SectionRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати всі розділи за порядковим номером.
    def get_all(self) -> list[Section]:
        stmt = select(Section).order_by(Section.number)
        return list(self.db.scalars(stmt).all())

    # Отримати розділ за кодом R1, R2 або R3.
    def get_by_id(self, section_id: str) -> Section | None:
        return self.db.get(Section, section_id)

    # Знайти розділ за номером.
    def get_by_number(self, number: int) -> Section | None:
        stmt = select(Section).where(Section.number == number)
        return self.db.scalar(stmt)

    # Додати розділ до поточної транзакції.
    def add(self, section: Section) -> Section:
        self.db.add(section)
        self.db.flush()
        return section

    # Зберегти змінену назву.
    def save(self, section: Section) -> Section:
        self.db.flush()
        return section
