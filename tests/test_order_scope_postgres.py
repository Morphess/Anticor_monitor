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
    def test_independent_registry_pagination_and_number_lookup(self):
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

                        created_at timestamptz NOT NULL
                    ) ON COMMIT DROP
                """))

                connection.execute(text("""
                    INSERT INTO orders
                        (id, number, title, created_at)
                    VALUES
                        ('OT1', '1', 'Перший', '2026-01-01'),
                        ('OT2', '2', 'Другий', '2026-01-02')
                """))

                with Session(bind=connection) as db:
                    repo = OrderRepository(db)

                    self.assertEqual([row.id for row in repo.list_orders(limit=1)], ["OT2"])
                    self.assertEqual([row.id for row in repo.list_orders(skip=1, limit=1)], ["OT1"])
                    self.assertEqual(repo.get_by_number("1").id, "OT1")
                    self.assertIsNone(repo.get_by_number("missing"))
        finally:
            engine.dispose()
