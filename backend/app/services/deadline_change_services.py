from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.deadline_change import DeadlineChange
from app.models.measure import Measure

from app.repositories.deadline_change_repository import DeadlineChangeRepository
from app.schemas.deadline_changes import (
    DeadlineChangeBase,
    DeadlineChangeCreate,
    DeadlineChangeUpdate,
)


# Помилка бізнес-логіки
class DeadlineChangeError(Exception):

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class DeadlineChangeService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = DeadlineChangeRepository(db)

    # READ — одне рішення
    def get_change(self, change_id: int) -> DeadlineChange:

        change = self.repo.get_by_id(change_id)

        if change is None:
            raise DeadlineChangeError("Рішення про перенесення не знайдено", 404)

        return change

    # READ — список рішень
    def list_changes(
        self, skip: int = 0, limit: int = 20, measure_id: str | None = None
    ) -> list[DeadlineChange]:

        return self.repo.list_changes(skip, limit, measure_id)

    # Перевірка існування заходу
    def check_measure(self, measure_id: str) -> Measure:

        measure = self.db.get(Measure, measure_id)

        if measure is None:
            raise DeadlineChangeError("Захід не існує")

        if measure.deadline_type != "date" or measure.deadline_on is None:
            raise DeadlineChangeError(
                "Для перенесення потрібен захід " "із конкретною датою завершення"
            )

        return measure

    # CREATE — нове рішення про перенесення
    def create_change(self, data: DeadlineChangeCreate, user_id: int) -> DeadlineChange:

        measure = self.check_measure(data.measure_id)

        # Знаходимо останнє перенесення
        latest = self.repo.get_latest(data.measure_id)

        # Визначаємо актуальний внутрішній строк
        current_deadline = (
            latest.new_deadline if latest is not None else measure.deadline_on
        )

        # Перевіряємо попередній строк
        if data.previous_deadline != current_deadline:
            raise DeadlineChangeError(f"Попередній строк має бути {current_deadline}")

        # Дата нового рішення не може передувати
        # попередньому рішенню про перенесення
        if latest is not None:
            if data.decision_date < latest.decision_date:
                raise DeadlineChangeError("Дата рішення раніша за попереднє рішення")

        # Створюємо запис
        change = DeadlineChange(**data.model_dump(), user_id=user_id)

        try:
            return self.repo.save(change)

        except IntegrityError as error:
            self.db.rollback()
            raise DeadlineChangeError("Не вдалося створити перенесення", 409) from error

    # UPDATE — редагування рішення
    def update_change(
        self, change_id: int, data: DeadlineChangeUpdate
    ) -> DeadlineChange:

        change = self.get_change(change_id)

        # Дозволяємо змінювати лише останнє рішення
        latest = self.repo.get_latest(change.measure_id)

        if latest is None or latest.id != change_id:
            raise DeadlineChangeError("Можна редагувати лише останнє перенесення", 409)

        changes = data.model_dump(exclude_unset=True)

        # Обов'язкові поля не можна очистити
        for field, value in changes.items():
            if value is None:
                raise DeadlineChangeError(f"Поле {field} не може бути null")

        # Об'єднуємо старі та нові значення
        merged = {
            field: changes.get(field, getattr(change, field))
            for field in DeadlineChangeBase.model_fields
        }

        # Повна перевірка дат
        try:
            validated = DeadlineChangeBase.model_validate(merged)

        except ValidationError as error:
            raise DeadlineChangeError(str(error.errors()[0]["msg"])) from error

        # Отримуємо строк перед останнім рішенням
        previous = self.repo.get_previous(change.measure_id)
        measure = self.check_measure(change.measure_id)

        expected_deadline = (
            previous.new_deadline if previous is not None else measure.deadline_on
        )

        if validated.previous_deadline != expected_deadline:
            raise DeadlineChangeError(f"Попередній строк має бути {expected_deadline}")

        if previous is not None:
            if validated.decision_date < previous.decision_date:
                raise DeadlineChangeError(
                    "Дата рішення раніша за попереднє перенесення"
                )

        # Застосовуємо зміни
        for field, value in changes.items():
            setattr(change, field, value)

        try:
            return self.repo.save(change)

        except IntegrityError as error:
            self.db.rollback()
            raise DeadlineChangeError("Не вдалося оновити перенесення", 409) from error

    # DELETE — видалення рішення
    def delete_change(self, change_id: int) -> None:

        change = self.get_change(change_id)

        # Не видаляємо проміжні рішення
        latest = self.repo.get_latest(change.measure_id)

        if latest is None or latest.id != change_id:
            raise DeadlineChangeError("Можна видалити лише останнє перенесення", 409)

        try:
            self.repo.delete(change)

        except IntegrityError as error:
            self.db.rollback()
            raise DeadlineChangeError("Рішення має пов'язані записи", 409) from error
