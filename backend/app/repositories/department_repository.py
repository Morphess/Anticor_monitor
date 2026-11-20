"""Запити до departments; управління транзакціями виконує сервіс."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department


class DepartmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Department]:
        return list(self.db.scalars(select(Department).order_by(Department.id)).all())

    # Спільний контракт із ProgramWorkflowRepository для DepartmentHierarchy.
    def all_departments(self) -> list[Department]:
        return self.get_all()

    def get_by_id(self, department_id: str) -> Department | None:
        return self.db.get(Department, department_id)

    def has_children(self, department_id: str) -> bool:
        stmt = select(Department.id).where(Department.parent_id == department_id).limit(1)
        return self.db.scalar(stmt) is not None

    def add(self, department: Department) -> None:
        self.db.add(department)
        self.db.flush()

    def save(self) -> None:
        self.db.flush()

    def delete(self, department: Department) -> None:
        self.db.delete(department)
        self.db.flush()
