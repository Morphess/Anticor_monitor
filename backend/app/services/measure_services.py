from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.measure import Measure
from app.models.program import Program
from app.models.risk import Risk
from app.models.section import Section
from app.models.user import User

from app.repositories.measure_repository import MeasureRepository
from app.schemas.measures import MeasureBase, MeasureCreate, MeasureUpdate


# Власна помилка для бізнес-логіки
class MeasureError(Exception):

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class MeasureService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = MeasureRepository(db)

    # Отримання одного заходу
    def get_measure(self, measure_id: str) -> Measure:

        measure = self.repo.get_by_id(measure_id)

        if measure is None:
            raise MeasureError("Захід не знайдено", 404)

        return measure

    # Отримання списку заходів
    def list_measures(
        self,
        skip: int = 0,
        limit: int = 20,
        program_id: str | None = None,
        section_id: str | None = None,
    ) -> list[Measure]:

        return self.repo.list_measures(skip, limit, program_id, section_id)

    # Перевірка зв'язків з іншими таблицями
    def _validate_links(self, data: MeasureBase, exclude_id: str | None = None) -> None:

        # Перевіряємо програму
        if self.db.get(Program, data.program_id) is None:
            raise MeasureError("Програма не існує")

        # Розділи R1/R2/R3 спільні для програм.
        section = self.db.get(Section, data.section_id)

        if section is None:
            raise MeasureError("Розділ не існує")

        # Перевіряємо корупційний ризик
        if data.risk_id is not None:

            risk = self.db.get(Risk, data.risk_id)

            if risk is None:
                raise MeasureError("Ризик не існує")

        # Перевіряємо відповідальний підрозділ
        if data.responsible_department_id is not None:

            department = self.db.get(Department, data.responsible_department_id)

            if department is None:
                raise MeasureError("Відповідальний підрозділ не існує")

        # Перевіряємо призначеного користувача
        if data.assigned_user_id is not None:

            user = self.db.get(User, data.assigned_user_id)

            if user is None:
                raise MeasureError("Призначений користувач не існує")

        # Перевіряємо унікальність номера
        if self.repo.number_taken(
            data.program_id,
            data.section_id,
            data.sequence_number,
            exclude_id=exclude_id,
        ):
            raise MeasureError(
                f"Номер {data.sequence_number} уже існує в розділі {section.number} цієї програми", 409
            )

    # CREATE
    def create_measure(self, data: MeasureCreate) -> Measure:

        # Перевіряємо унікальність ID
        if self.repo.get_by_id(data.id) is not None:
            raise MeasureError("Захід із таким ID уже існує", 409)

        # Перевіряємо зовнішні ключі
        self._validate_links(data)

        # Створюємо ORM-об'єкт
        measure = Measure(**data.model_dump())

        try:
            return self.repo.save(measure)

        except IntegrityError as exc:
            self.db.rollback()
            raise MeasureError(
                "Не вдалося зберегти захід: " "перевір унікальність і зв'язки", 409
            ) from exc

    # UPDATE
    def update_measure(self, measure_id: str, data: MeasureUpdate) -> Measure:

        measure = self.get_measure(measure_id)

        # Беремо тільки передані поля
        changes = data.model_dump(exclude_unset=True)

        # Обов'язкові поля не можуть бути NULL
        non_nullable = {
            "program_id",
            "section_id",
            "sequence_number",
            "description",
            "deadline_description",
            "deadline_type",
            "completion_indicator",
            "required_evidence",
            "resources",
        }

        if any(key in non_nullable and value is None for key, value in changes.items()):
            raise MeasureError("Обов'язкові поля не можуть бути null")

        # Об'єднуємо старі та нові значення
        merged = {
            key: changes.get(key, getattr(measure, key))
            for key in MeasureBase.model_fields
        }

        # Перевіряємо строк виконання
        try:
            validated = MeasureBase.model_validate(merged)

        except ValidationError as exc:
            raise MeasureError(
                "Некоректні дані заходу, перевір строк та дату", 422
            ) from exc

        # Перевіряємо всі зв'язки
        self._validate_links(validated, exclude_id=measure_id)

        # Оновлюємо потрібні поля
        for key, value in changes.items():
            setattr(measure, key, value)

        try:
            return self.repo.save(measure)

        except IntegrityError as exc:
            self.db.rollback()
            raise MeasureError("Не вдалося оновити захід: конфлікт даних", 409) from exc

    # DELETE
    def delete_measure(self, measure_id: str) -> None:

        measure = self.get_measure(measure_id)

        try:
            self.repo.delete(measure)

        except IntegrityError as exc:
            self.db.rollback()
            raise MeasureError(
                "Захід має пов'язані записи; " "видалення заборонено", 409
            ) from exc
