from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department


class DepartmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Department]:
        statement = select(Department).order_by(Department.id)
        return list(self.db.scalars(statement).all())

    def get_by_id(self, department_id: str) -> Department | None:
        return self.db.get(Department, department_id)

    def add(self, department: Department) -> None:
        self.db.add(department)
        self.db.flush()

    def save(self) -> None:
        self.db.flush()

    def delete(self, department: Department) -> None:
        self.db.delete(department)
        self.db.flush()