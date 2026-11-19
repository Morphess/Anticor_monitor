"""CRUD наказів для розробника + перевірка номера для EvidenceService."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_version import OrderVersion
from app.models.evidence import Evidence
from sqlalchemy import select
from app.repositories.order_repository import OrderRepository
from app.schemas.orders import OrderCheckStatus, OrderCreate, OrderUpdate


class OrderError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = OrderRepository(db)

    def get_order(self, order_id: str) -> Order:
        order = self.repo.get_by_id(order_id)
        if order is None:
            raise OrderError("Наказ не знайдено", 404)
        return order

    def list_orders(self, *, skip: int = 0, limit: int = 20) -> list[Order]:
        return self.repo.list_orders(skip=skip, limit=limit)

    def create_order(self, data: OrderCreate) -> Order:
        if self.repo.get_by_id(data.id) is not None:
            raise OrderError("Наказ із таким ID уже існує", 409)
        if self.repo.get_by_number(data.number) is not None:
            raise OrderError("Наказ із таким номером уже існує", 409)
        order = Order(**data.model_dump())
        try:
            return self.repo.save(order)
        except IntegrityError as exc:
            self.db.rollback()
            raise OrderError("ID або номер наказу вже зайнятий", 409) from exc

    def update_order(self, order_id: str, data: OrderUpdate) -> Order:
        order = self.get_order(order_id)
        changes = data.model_dump(exclude_unset=True)
        has_version = self.db.scalar(select(OrderVersion.id).where(
            OrderVersion.order_id == order_id).limit(1)) is not None
        if has_version and any(
            name in changes and changes[name] != getattr(order, name)
            for name in ("number", "title", "issued_on", "document_url")
        ):
            raise OrderError(
                "Наказ має збережені версії: не перезаписуй його дані через PATCH; "
                "завантаж нову версію документа", 409,
            )
        if "number" in changes and changes["number"] != order.number:
            used = self.db.scalar(select(Evidence.id).where(
                Evidence.order_number == order.number).limit(1))
            if used is not None:
                raise OrderError("Номер наказу вже використано в підтвердженнях", 409)
        for name in ("number", "title"):
            if name in changes and changes[name] is None:
                raise OrderError(f"Поле '{name}' не може бути null", 422)
        if "number" in changes and changes["number"] != order.number:
            if self.repo.get_by_number(changes["number"]) is not None:
                raise OrderError("Наказ із таким номером уже існує", 409)
        for name, value in changes.items():
            setattr(order, name, value)
        try:
            return self.repo.save(order)
        except IntegrityError as exc:
            self.db.rollback()
            raise OrderError("Конфлікт ID або номера наказу", 409) from exc

    def delete_order(self, order_id: str) -> None:
        order = self.get_order(order_id)
        has_version = self.db.scalar(select(OrderVersion.id).where(
            OrderVersion.order_id == order_id).limit(1)) is not None
        has_evidence = self.db.scalar(select(Evidence.id).where(
            Evidence.order_number == order.number).limit(1)) is not None
        if has_version or has_evidence:
            raise OrderError("Не можна видалити наказ із версіями або підтвердженнями", 409)
        try:
            self.repo.delete(order)
        except IntegrityError as exc:
            self.db.rollback()
            raise OrderError("Не вдалося видалити наказ: є залежні записи", 409) from exc

    def verify_number(self, number: str | None) -> OrderCheckStatus:
        """Пошук за точним номером (після обрізання крайніх пробілів).

        Не створює наказ та не забороняє збереження Evidence.
        """
        cleaned = number.strip() if number is not None else ""
        if not cleaned:
            return "not_provided"
        return "found" if self.repo.get_by_number(cleaned) else "not_found"
