"""Репозиторій незалежного реєстру наказів."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, order_id: str) -> Order | None:
        return self.db.get(Order, order_id)

    def get_by_number(self, number: str) -> Order | None:
        return self.db.scalar(select(Order).where(Order.number == number))

    def list_orders(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Order]:
        stmt = (
            select(Order)
            .order_by(Order.created_at.desc(), Order.id.asc())
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt))

    def save(self, order: Order) -> Order:
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def delete(self, order: Order) -> None:
        self.db.delete(order)
        self.db.commit()
