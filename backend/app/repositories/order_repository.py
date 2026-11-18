from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.measure import Measure
from app.models.order import Order


class OrderRepository:

    def __init__(self, db: Session):
        self.db = db

    # READ — отримати наказ за ID
    def get_by_id(self, order_id: str) -> Order | None:

        return self.db.get(Order, order_id)

    # READ — список наказів із фільтрами
    def list_orders(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        measure_id: str | None = None,
        program_id: str | None = None,
        assigned_user_id: int | None = None,
    ) -> list[Order]:

        stmt = select(Order)

        # Обмежуємо перелік доступними заходами, якщо треба
        if program_id is not None or assigned_user_id is not None:

            stmt = stmt.join(Measure, Order.measure_id == Measure.id)

            if program_id is not None:
                stmt = stmt.where(Measure.program_id == program_id)

            if assigned_user_id is not None:
                stmt = stmt.where(Measure.assigned_user_id == assigned_user_id)

        # Фільтрація за конкретним заходом
        if measure_id is not None:
            stmt = stmt.where(Order.measure_id == measure_id)

        stmt = (
            stmt.order_by(Order.created_at.desc(), Order.id.asc())
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())

    # CREATE / UPDATE — збереження наказу
    def save(self, order: Order) -> Order:

        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        return order

    # DELETE — видалення наказу
    def delete(self, order: Order) -> None:

        self.db.delete(order)
        self.db.commit()
