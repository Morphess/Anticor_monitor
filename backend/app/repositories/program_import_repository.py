"""Лише операції доступу до даних для атомарного імпорту програми."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.measure import Measure
from app.models.program import Program
from app.models.risk import Risk
from app.models.section import Section
from app.models.user import User


class ProgramImportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def program(self, program_id: str) -> Program | None:
        return self.db.get(Program, program_id)

    def section(self, section_id: str) -> Section | None:
        return self.db.get(Section, section_id)

    def section_with_number(self, number: int) -> Section | None:
        return self.db.scalar(select(Section).where(Section.number == number))

    def measure(self, measure_id: str) -> Measure | None:
        return self.db.get(Measure, measure_id)

    def department(self, department_id: str) -> Department | None:
        return self.db.get(Department, department_id)

    def all_departments(self) -> list[Department]:
        # Використовується DepartmentHierarchy: parent_id, без здогадок за префіксом ID.
        return list(self.db.scalars(select(Department).order_by(Department.id)))

    def risk(self, risk_id: str) -> Risk | None:
        return self.db.get(Risk, risk_id)

    def user(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def add(self, instance: Any) -> None:
        self.db.add(instance)

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
