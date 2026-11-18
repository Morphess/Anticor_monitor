"""Бізнес-логіка створення, перегляду та редагування звітності."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.execution import Execution
from app.models.measure import Measure
from app.repositories.execution_repository import ExecutionRepository
from app.schemas.execution import ExecutionCreate, ExecutionUpdate

from sqlalchemy.exc import SQLAlchemyError


class ExecutionNotFoundError(Exception):
    pass


class ExecutionAlreadyExistsError(Exception):
    pass


class MeasureNotFoundError(Exception):
    pass


class ExecutionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ExecutionRepository()

    def get(self, measure_id: str, period: str) -> Execution:
        execution = self.repo.get(self.db, measure_id, period)
        if execution is None:
            raise ExecutionNotFoundError("Звіт за цим заходом і періодом не знайдено")
        return execution

    def list(
        self,
        *,
        measure_id: str | None = None,
        period: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Execution]:
        return self.repo.list(
            self.db,
            measure_id=measure_id,
            period=period,
            status=status,
            offset=offset,
            limit=limit,
        )

    def create(self, data: ExecutionCreate) -> Execution:
        if self.db.get(Measure, data.measure_id) is None:
            raise MeasureNotFoundError("Захід не знайдено")
        if self.repo.get(self.db, data.measure_id, data.period) is not None:
            raise ExecutionAlreadyExistsError(
                "Звіт за цим заходом і періодом вже існує"
            )

        # Службові поля submitted_by_user_id / approved_by_coordinator
        # не приймаємо від клієнта: потрібен окремий перевірений auth-flow.
        execution = Execution(**data.model_dump())
        self.repo.add(self.db, execution)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            if self._is_unique_violation(error):
                raise ExecutionAlreadyExistsError(
                    "Звіт за цим заходом і періодом вже існує"
                ) from error
            if self._is_foreign_key_violation(error):
                raise MeasureNotFoundError("Захід не знайдено") from error
            raise
        self.db.refresh(execution)
        return execution

    def update(self, measure_id: str, period: str, data: ExecutionUpdate) -> Execution:
        execution = self.get(measure_id, period)
        changes = data.model_dump(exclude_unset=True)
        if changes:
            self.repo.update(execution, changes)
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                raise
            self.db.refresh(execution)
        return execution

    def delete(self, measure_id: str, period: str) -> None:
        execution = self.get(measure_id, period)
        self.repo.delete(self.db, execution)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise

    def update_approval(
        self,
        measure_id: str,
        period: str,
        approved: bool,
    ) -> Execution:
        """Погодження або скасування погодження звіту."""

        # Отримуємо звіт за складеним первинним ключем.
        execution = self.get(measure_id, period)

        # Оновлюємо стан погодження.
        self.repo.set_approval(
            execution,
            approved,
        )

        try:
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise

        self.db.refresh(execution)

        return execution

    @staticmethod
    def _is_unique_violation(error: IntegrityError) -> bool:
        orig = error.orig
        code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        return code == "23505" or "UNIQUE constraint failed" in str(orig)

    @staticmethod
    def _is_foreign_key_violation(error: IntegrityError) -> bool:
        orig = error.orig
        code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        return code == "23503" or "FOREIGN KEY constraint failed" in str(orig)
