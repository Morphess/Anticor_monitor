from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.department import Department
from app.repositories.department_repository import DepartmentRepository
from app.schemas.departments import DepartmentCreate, DepartmentUpdate


class DepartmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = DepartmentRepository(db)

    def _get_or_404(self, department_id: str) -> Department:
        department = self.repository.get_by_id(department_id)
        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Підрозділ не знайдено",
            )
        return department

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Поле '{field}' не може бути порожнім",
            )
        return cleaned

    def get_all(self) -> list[Department]:
        return self.repository.get_all()

    def get_by_id(self, department_id: str) -> Department:
        return self._get_or_404(department_id)

    def create(self, data: DepartmentCreate) -> Department:
        department_id = self._required_text(data.id, "id")
        name = self._required_text(data.name, "name")
        department_type = self._required_text(
            data.department_type, "department_type"
        )

        if self.repository.get_by_id(department_id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Підрозділ із таким кодом уже існує",
            )

        department = Department(
            id=department_id,
            name=name,
            department_type=department_type,
            notes=data.notes,
        )
        try:
            self.repository.add(department)
            self.db.commit()
            self.db.refresh(department)
            return department
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Операцію неможливо виконати через обмеження бази даних",
            ) from exc
        except Exception:
            self.db.rollback()
            raise

    def update(
        self, department_id: str, data: DepartmentUpdate
    ) -> Department:
        department = self._get_or_404(department_id)
        changes = data.model_dump(exclude_unset=True)

        for field, value in changes.items():
            if value is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Поле '{field}' не може бути null",
                )
            if field in {"name", "department_type"}:
                value = self._required_text(value, field)
            setattr(department, field, value)

        try:
            self.repository.save()
            self.db.commit()
            self.db.refresh(department)
            return department
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Операцію неможливо виконати через обмеження бази даних",
            ) from exc
        except Exception:
            self.db.rollback()
            raise

    def delete(self, department_id: str) -> None:
        department = self._get_or_404(department_id)
        try:
            self.repository.delete(department)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Підрозділ використовується в інших записах",
            ) from exc
        except Exception:
            self.db.rollback()
            raise