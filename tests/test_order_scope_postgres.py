import os
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.models
from app.repositories.order_repository import OrderRepository


@unittest.skipUnless(
    os.environ.get("ORDER_TEST_DATABASE_URL"),
    "Не задано URL окремої тестової PostgreSQL",
)
class OrderScopePostgresTests(unittest.TestCase):
    def test_filters_orders_before_pagination(self):
        engine = create_engine(os.environ["ORDER_TEST_DATABASE_URL"])

        try:
            with engine.begin() as connection:
                # Тимчасова таблиця існує лише в цьому з'єднанні.
                connection.execute(text("""
                    CREATE TEMPORARY TABLE orders (
                        id varchar(50) PRIMARY KEY,
                        number varchar(150) NOT NULL,
                        title text NOT NULL,
                        issued_on date,
                        document_url text,
                        measure_id varchar(8) NOT NULL,
                        created_at timestamptz NOT NULL
                    ) ON COMMIT DROP
                """))

                connection.execute(text("""
                    INSERT INTO orders
                        (id, number, title, measure_id, created_at)
                    VALUES
                        ('OT1', '1', 'Дозволений', 'M01', '2026-01-01'),
                        ('OT2', '2', 'Чужий', 'M02', '2026-01-02')
                """))

                with Session(bind=connection) as db:
                    repo = OrderRepository(db)

                    # Чужий наказ новіший: фільтр має спрацювати до limit.
                    visible = repo.list_orders(
                        measure_ids=["M01"],
                        limit=1,
                    )
                    self.assertEqual([order.id for order in visible], ["OT1"])

                    none = repo.list_orders(measure_ids=[])
                    self.assertEqual(none, [])

                    combined = repo.list_orders(
                        measure_id="M02",
                        measure_ids=["M01"],
                    )
                    self.assertEqual(combined, [])
        finally:
            engine.dispose()