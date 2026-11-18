from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.department import Department
from app.schemas.departments import DepartmentCreate, DepartmentUpdate


class DepartmentAlreadyExistsError(Exception):
    pass


class DepartmentNotFoundError(Exception):
    pass


class DepartmentUpdateError(Exception):
    pass


class DepartmentService:
    def __init__(self, db: Session):
        self.db = db

    def list_departments(self) -> list[Department]:
        return list(
            self.db.scalars(select(Department).order_by(Department.id)).all()
        )

    def create_department(self, data: DepartmentCreate) -> Department:
        if self.db.get(Department, data.id) is not None:
            raise DepartmentAlreadyExistsError("Підрозділ із таким кодом уже існує")

        department = Department(**data.model_dump())
        self.db.add(department)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise DepartmentAlreadyExistsError(
                "Підрозділ із таким кодом уже існує"
            ) from error

        self.db.refresh(department)
        return department

    def update_department(
        self, department_id: str, data: DepartmentUpdate
    ) -> Department:
        department = self.db.get(Department, department_id)
        if department is None:
            raise DepartmentNotFoundError("Підрозділ не знайдено")

        changes = data.model_dump(exclude_unset=True)
        if not changes:
            return department
        if any(value is None for value in changes.values()):
            raise DepartmentUpdateError("Поля підрозділу не можуть бути порожніми")

        for field, value in changes.items():
            setattr(department, field, value)

        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise DepartmentUpdateError("Не вдалося оновити підрозділ") from error

        self.db.refresh(department)
        return department
