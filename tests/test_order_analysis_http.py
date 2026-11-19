import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("APP_NAME", "BorderGroup Test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://unused:unused@127.0.0.1/unused",
)
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "synthetic-test-key-for-hs256-at-least-32-bytes",
)

from app.api.orders import router
from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.schemas.orders import OrderAnalysisRead


class OrderAnalysisHttpTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=7, role_id="KOORD")
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_db] = lambda: Mock()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

        self.order = SimpleNamespace(id="O01", measure_id="M01")
        self.measure = SimpleNamespace(id="M01", program_id="P01")
        self.result = OrderAnalysisRead(
            order_id="O01",
            file_name="order.txt",
            model="test-model",
            analysis="Тестовий звіт",
            text_truncated=False,
        )

    def send_file(self):
        return self.client.post(
            "/api/orders/O01/analyze",
            files={"file": ("order.txt", b"Test document", "text/plain")},
        )

    def test_coordinator_can_analyze_visible_measure(self):
        with (
            patch("app.api.orders.OrderService") as order_service,
            patch("app.api.orders._get_measure", return_value=self.measure),
            patch("app.api.orders.ProgramWorkflowService") as workflow,
            patch(
                "app.api.orders.analyze_order_document",
                new_callable=AsyncMock,
                return_value=self.result,
            ),
        ):
            order_service.return_value.get_order.return_value = self.order
            workflow.return_value.program_measures.return_value = [{"id": "M01"}]

            response = self.send_file()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"], "Тестовий звіт")

    def test_coordinator_cannot_analyze_invisible_measure(self):
        with (
            patch("app.api.orders.OrderService") as order_service,
            patch("app.api.orders._get_measure", return_value=self.measure),
            patch("app.api.orders.ProgramWorkflowService") as workflow,
            patch(
                "app.api.orders.analyze_order_document",
                new_callable=AsyncMock,
            ) as analyze,
        ):
            order_service.return_value.get_order.return_value = self.order
            workflow.return_value.program_measures.return_value = [{"id": "OTHER"}]

            response = self.send_file()

        self.assertEqual(response.status_code, 403)
        analyze.assert_not_awaited()

    def test_executor_cannot_analyze(self):
        self.user.role_id = "VYK"

        with (
            patch("app.api.orders.OrderService") as order_service,
            patch("app.api.orders._get_measure", return_value=self.measure),
            patch(
                "app.api.orders.analyze_order_document",
                new_callable=AsyncMock,
            ) as analyze,
        ):
            order_service.return_value.get_order.return_value = self.order
            response = self.send_file()

        self.assertEqual(response.status_code, 403)
        analyze.assert_not_awaited()
    
    def test_coordinator_lists_orders_for_visible_measures(self):
        self.user.program_id = None
        self.user.department_id = "P01"

        with (
            patch("app.api.orders.ProgramWorkflowService") as workflow,
            patch("app.api.orders.OrderService") as order_service,
        ):
            workflow.return_value.my_programs.return_value = [{"id": "PR01"}]
            workflow.return_value.program_measures.return_value = [
                {"id": "M01"},
                {"id": "M02"},
            ]
            order_service.return_value.list_orders.return_value = []

            response = self.client.get("/api/orders/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        order_service.return_value.list_orders.assert_called_once_with(
            skip=0,
            limit=20,
            measure_id=None,
            measure_ids=["M01", "M02"],
        )

    def test_coordinator_without_visible_measures_gets_empty_scope(self):
        self.user.program_id = None
        self.user.department_id = "P01"

        with (
            patch("app.api.orders.ProgramWorkflowService") as workflow,
            patch("app.api.orders.OrderService") as order_service,
        ):
            workflow.return_value.my_programs.return_value = []
            order_service.return_value.list_orders.return_value = []

            response = self.client.get("/api/orders/")

        self.assertEqual(response.status_code, 200)
        order_service.return_value.list_orders.assert_called_once_with(
            skip=0,
            limit=20,
            measure_id=None,
            measure_ids=[],
        )