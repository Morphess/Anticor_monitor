from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.measure import Measure
from app.models.order import Order

from app.repositories.order_repository import OrderRepository
from app.schemas.orders import OrderCreate, OrderUpdate


# Помилка бізнес-логіки наказів
class OrderError(Exception):

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class OrderService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = OrderRepository(db)

    # READ — отримати наказ
    def get_order(self, order_id: str) -> Order:

        order = self.repo.get_by_id(order_id)

        if order is None:
            raise OrderError("Наказ не знайдено", 404)

        return order

    # READ — отримати список наказів
    def list_orders(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        measure_id: str | None = None,
        program_id: str | None = None,
        assigned_user_id: int | None = None,
        measure_ids: list[str] | None = None,
    ) -> list[Order]:

        return self.repo.list_orders(
            skip=skip,
            limit=limit,
            measure_id=measure_id,
            program_id=program_id,
            assigned_user_id=assigned_user_id,
            measure_ids=measure_ids,
        )

    # Перевірка існування заходу
    def check_measure(self, measure_id: str) -> Measure:

        measure = self.db.get(Measure, measure_id)

        if measure is None:
            raise OrderError("Захід із таким ID не існує", 422)

        return measure

    # CREATE — створення наказу
    def create_order(self, data: OrderCreate) -> Order:

        # Перевірка унікальності ID
        if self.repo.get_by_id(data.id) is not None:
            raise OrderError("Наказ із таким ID вже існує", 409)

        # Перевірка пов'язаного заходу
        self.check_measure(data.measure_id)

        # Створення ORM-об'єкта
        order = Order(**data.model_dump())

        try:
            return self.repo.save(order)

        except IntegrityError as exc:
            self.db.rollback()

            raise OrderError("Конфлікт даних під час створення наказу", 409) from exc

    # UPDATE — редагування наказу
    def update_order(self, order_id: str, data: OrderUpdate) -> Order:

        order = self.get_order(order_id)

        # Отримуємо лише передані поля
        changes = data.model_dump(exclude_unset=True)

        # Обов'язкові поля моделі
        required_fields = {"number", "title", "measure_id"}

        # Забороняємо очищення обов'язкових полів
        for key, value in changes.items():

            if key in required_fields and value is None:
                raise OrderError(f"Поле '{key}' не може бути null")

        # Якщо змінюємо захід, перевіряємо його
        if "measure_id" in changes:
            self.check_measure(changes["measure_id"])

        # Оновлюємо ORM-об'єкт
        for key, value in changes.items():
            setattr(order, key, value)

        try:
            return self.repo.save(order)

        except IntegrityError as exc:
            self.db.rollback()

            raise OrderError("Конфлікт даних під час оновлення наказу", 409) from exc

    # DELETE — видалення наказу
    def delete_order(self, order_id: str) -> None:

        order = self.get_order(order_id)

        try:
            self.repo.delete(order)

        except IntegrityError as exc:
            self.db.rollback()

            raise OrderError(
                "Наказ не вдалося видалити: існують залежні записи", 409
            ) from exc
