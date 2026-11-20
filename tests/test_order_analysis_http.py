"""The coordinator analyzes an execution's pinned version, never an arbitrary upload."""
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

for key, value in {"APP_NAME":"Test", "DEBUG":"false", "SQL_ECHO":"false",
                   "DATABASE_URL":"postgresql+psycopg://unused:unused@127.0.0.1/unused",
                   "JWT_SECRET_KEY":"synthetic-test-key-at-least-32-bytes"}.items():
    os.environ.setdefault(key, value)

from app.api.execution import router
from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.schemas.orders import OrderAnalysisRead
from app.services.execution_services import ExecutionError
from app.services.order_analysis_services import OrderAnalysisError


class ExecutionAnalysisHttpTests(unittest.TestCase):
    def setUp(self):
        self.actor = SimpleNamespace(id=7, role_id="KOORD", department_id="D01")
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: self.actor
        app.dependency_overrides[get_db] = lambda: Mock()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.result = OrderAnalysisRead(order_id="O01", file_name="pinned.pdf",
             model="test-model", analysis="Synthetic comparison", text_truncated=False)
        self.inputs = patch("app.api.execution.analysis_input", return_value=(
            SimpleNamespace(id="O01", number="TEST", title="Test", issued_on=None), SimpleNamespace(id="M01", description="Training", deadline_on=None, deadline_description="Ongoing", completion_indicator="Report", required_evidence="Report"), "pinned.pdf", b"PDF", 3, "a"*64))
        self.get_input = self.inputs.start()
        self.addCleanup(self.inputs.stop)
        self.analysis = patch("app.api.execution.analyze_order_document", new_callable=AsyncMock, return_value=self.result)
        self.analyze = self.analysis.start()
        self.addCleanup(self.analysis.stop)
        repo_patch = patch("app.api.execution.ExecutionAnalysisRepository")
        self.repo = repo_patch.start().return_value
        self.addCleanup(repo_patch.stop)
        self.repo.latest.return_value = None
        self.repo.try_lock.return_value = True
        self.saved = SimpleNamespace(**self.result.model_dump(), execution_id=11,
            order_version_id=3, submitted_sha256="a"*64, analysis_id=8,
            created_at=datetime.now(timezone.utc))
        self.repo.save.return_value = self.saved
        ctx_patch = patch("app.api.execution.saved_analysis_context", return_value=(3, "a"*64, "f"*64))
        self.saved_context = ctx_patch.start()
        self.addCleanup(ctx_patch.stop)

    def send(self, force=False):
        return self.client.post("/api/executions/11/analyze"+("?force=true" if force else ""))

    def test_coordinator_analyzes_pinned_submission(self):
        response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order_version_id"], 3)
        self.assertEqual(response.json()["execution_id"], 11)
        self.analyze.assert_awaited_once()
        self.assertEqual(self.analyze.await_args.args[2:], ("pinned.pdf", b"PDF"))

    def test_main_coordinator_can_analyze(self):
        self.actor.role_id = "MAIN_KOORD"
        self.assertEqual(self.send().status_code, 200)

    def test_executor_and_admin_cannot_analyze(self):
        for role in ("VYK", "ADMIN", "KER", "ANAL"):
            self.actor.role_id = role
            self.assertEqual(self.send().status_code, 403)
        self.get_input.assert_not_called()
        self.analyze.assert_not_awaited()

    def test_invisible_measure_is_denied_before_model_call(self):
        self.get_input.side_effect = HTTPException(403, "Denied")
        self.assertEqual(self.send().status_code, 403)
        self.analyze.assert_not_awaited()

    def test_missing_or_changed_pinned_document_is_rejected(self):
        for code in (404, 409):
            self.get_input.side_effect = ExecutionError("Invalid document", code)
            self.assertEqual(self.send().status_code, code)
        self.analyze.assert_not_awaited()

    def test_model_timeout_and_unavailable_are_reported(self):
        for code in (504, 503):
            self.analyze.side_effect = OrderAnalysisError("Model unavailable", code)
            self.assertEqual(self.send().status_code, code)

    def test_legacy_arbitrary_upload_endpoint_is_absent(self):
        self.assertEqual(self.client.post("/api/orders/O01/analyze").status_code, 404)

    def test_saved_report_is_returned_without_model_call(self):
        self.repo.latest.return_value = self.saved
        self.assertEqual(self.send().json()["analysis_id"], 8)
        self.analyze.assert_not_awaited()
        self.repo.try_lock.assert_not_called()

    def test_force_generates_and_saves_new_report(self):
        self.repo.latest.return_value = self.saved
        self.assertEqual(self.send(force=True).status_code, 200)
        self.analyze.assert_awaited_once()
        self.repo.save.assert_called_once()

    def test_concurrent_generation_is_rejected(self):
        self.repo.try_lock.return_value = False
        self.assertEqual(self.send().status_code, 409)
        self.analyze.assert_not_awaited()

    def test_get_saved_report_never_calls_model_or_reads_file(self):
        self.repo.latest.return_value = self.saved
        response = self.client.get("/api/executions/11/analysis")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis_id"], 8)
        self.get_input.assert_not_called()
        self.analyze.assert_not_awaited()

    def test_get_without_matching_report_returns_204(self):
        response = self.client.get("/api/executions/11/analysis")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

    def test_get_denies_roles_and_invisible_measure_before_cache(self):
        for role in ("VYK", "ADMIN", "KER", "ANAL"):
            self.actor.role_id = role
            self.assertEqual(self.client.get("/api/executions/11/analysis").status_code, 403)
        self.repo.latest.assert_not_called()
        self.saved_context.assert_not_called()
        self.actor.role_id = "KOORD"
        self.saved_context.side_effect = HTTPException(403, "Denied")
        self.assertEqual(self.client.get("/api/executions/11/analysis").status_code, 403)
        self.repo.latest.assert_not_called()
