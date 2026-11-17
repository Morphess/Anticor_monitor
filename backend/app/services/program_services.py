from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.program import Program
from app.repositories.program_repository import ProgramRepository
from app.schemas.programs import (
    ProgramCreate,
    ProgramUpdate,
)


class ProgramService:

    def __init__(self, db: Session):
        self.db = db
        self.repository = ProgramRepository(db)

    # ------------------------------------------
    # Внутрішні перевірки
    # ------------------------------------------

    def _get_or_404(self, program_id: str) -> Program:
        program = self.repository.get_by_id(program_id)

        if program is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Антикорупційну програму не знайдено",
            )

        return program

    def _check_department(
        self,
        department_id: str | None,
    ) -> None:

        if department_id is None:
            return

        department = self.db.get(
            Department,
            department_id,
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=("Підрозділ-координатор " f"'{department_id}' не знайдений"),
            )

    def _commit(self) -> None:
        try:
            self.db.commit()

        except IntegrityError as exc:
            self.db.rollback()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Операцію неможливо виконати через "
                    "обмеження цілісності бази даних"
                ),
            ) from exc

    # ------------------------------------------
    # Отримати всі програми
    # ------------------------------------------

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Program]:

        return self.repository.get_all(
            skip=skip,
            limit=limit,
        )

    # ------------------------------------------
    # Отримати одну програму
    # ------------------------------------------

    def get_by_id(self, program_id: str) -> Program:
        return self._get_or_404(program_id)

    # ------------------------------------------
    # Створити програму
    # ------------------------------------------

    def create(
        self,
        data: ProgramCreate,
    ) -> Program:

        existing = self.repository.get_by_id(data.id)

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"Програма з кодом '{data.id}' " "вже існує"),
            )

        self._check_department(data.coordinator_department_id)

        program = Program(**data.model_dump())

        try:
            self.repository.create(program)
            self._commit()
            self.db.refresh(program)
            return program

        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------
    # Оновити програму
    # ------------------------------------------

    def update(
        self,
        program_id: str,
        data: ProgramUpdate,
    ) -> Program:

        program = self._get_or_404(program_id)

        changes = data.model_dump(exclude_unset=True)

        # Ці поля в PostgreSQL мають NOT NULL.
        required_fields = {
            "title",
            "organization_name",
            "start_date",
            "end_date",
            "approval_reference",
            "approval_status",
            "has_restricted_information",
            "goals",
            "notes",
        }

        for field, value in changes.items():
            if field in required_fields and value is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Поле '{field}' не може бути null",
                )

        start_date = changes.get(
            "start_date",
            program.start_date,
        )

        end_date = changes.get(
            "end_date",
            program.end_date,
        )

        if end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=("Дата завершення програми не може " "бути раніше дати початку"),
            )

        if "coordinator_department_id" in changes:
            self._check_department(changes["coordinator_department_id"])

        for field, value in changes.items():
            setattr(program, field, value)

        try:
            self.repository.update(program)
            self._commit()
            self.db.refresh(program)
            return program

        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------
    # Видалити програму
    # ------------------------------------------

    def delete(self, program_id: str) -> None:

        program = self._get_or_404(program_id)

        try:
            self.repository.delete(program)
            self._commit()

        except Exception:
            self.db.rollback()
            raise
