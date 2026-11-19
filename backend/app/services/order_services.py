"""Бізнес-логіка наказів і перевірка номерів."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Order
from app.repositories.order_repository import OrderRepository
from app.schemas.orders import (
    OrderCheckStatus,
    OrderCreate,
    OrderUpdate,
)


class OrderError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 422,
    ):
        super().__init__(message)
        self.status_code = status_code


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = OrderRepository(db)

    # READ — один наказ
    def get_order(self, order_id: str) -> Order:
        order = self.repo.get_by_id(order_id)

        if order is None:
            raise OrderError("Наказ не знайдено", 404)

        return order

    # READ — список наказів
    def list_orders(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Order]:
        return self.repo.list_orders(
            skip=skip,
            limit=limit,
        )

    # CREATE — додавання наказу до реєстру
    def create_order(self, data: OrderCreate) -> Order:
        if self.repo.get_by_id(data.id) is not None:
            raise OrderError(
                "Наказ із таким ID уже існує",
                409,
            )

        if self.repo.get_by_number(data.number) is not None:
            raise OrderError(
                "Наказ із таким номером уже існує",
                409,
            )

        order = Order(**data.model_dump())

        try:
            return self.repo.save(order)
        except IntegrityError as exc:
            self.db.rollback()
            raise OrderError(
                "ID або номер наказу вже зайнятий",
                409,
            ) from exc

    # UPDATE — редагування наказу
    def update_order(
        self,
        order_id: str,
        data: OrderUpdate,
    ) -> Order:
        order = self.get_order(order_id)
        changes = data.model_dump(exclude_unset=True)

        for name in ("number", "title"):
            if name in changes and changes[name] is None:
                raise OrderError(
                    f"Поле '{name}' не може бути null",
                    422,
                )

        if "number" in changes and changes["number"] != order.number:
            if self.repo.get_by_number(changes["number"]) is not None:
                raise OrderError(
                    "Наказ із таким номером уже існує",
                    409,
                )

        for name, value in changes.items():
            setattr(order, name, value)

        try:
            return self.repo.save(order)
        except IntegrityError as exc:
            self.db.rollback()
            raise OrderError(
                "Конфлікт ID або номера наказу",
                409,
            ) from exc

    # DELETE — видалення наказу
    def delete_order(self, order_id: str) -> None:
        order = self.get_order(order_id)

        try:
            self.repo.delete(order)
        except IntegrityError as exc:
            self.db.rollback()
            raise OrderError(
                "Не вдалося видалити наказ: є залежні записи",
                409,
            ) from exc

    # VERIFY — перевірка номера для Evidence
    def verify_number(
        self,
        number: str | None,
    ) -> OrderCheckStatus:
        cleaned = number.strip() if number is not None else ""

        if not cleaned:
            return "not_provided"

        if self.repo.get_by_number(cleaned) is not None:
            return "found"

        return "not_found"
