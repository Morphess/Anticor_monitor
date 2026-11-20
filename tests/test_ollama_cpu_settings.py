"""CPU response budget and explicit output truncation without running a model."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from pydantic import ValidationError

for key, value in {"APP_NAME":"Test", "DEBUG":"false", "SQL_ECHO":"false",
                   "DATABASE_URL":"postgresql+psycopg://unused:unused@127.0.0.1/unused",
                   "JWT_SECRET_KEY":"synthetic-test-key-at-least-32-bytes"}.items():
    os.environ.setdefault(key, value)
from app.core.config import Settings, settings
from app.services.order_analysis_services import analyze_order_document


class OllamaSettingsTests(unittest.TestCase):
    def config(self, **overrides):
        return Settings(_env_file=None, APP_NAME="Test", DEBUG=False, SQL_ECHO=False,
            DATABASE_URL="postgresql+psycopg://unused:unused@127.0.0.1/unused",
            JWT_SECRET_KEY="synthetic-test-key-at-least-32-bytes", **overrides)

    def test_cpu_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self.config()
        self.assertEqual(cfg.OLLAMA_TIMEOUT_SECONDS, 600)
        self.assertEqual(cfg.OLLAMA_NUM_PREDICT, 768)

    def test_environment_overrides(self):
        with patch.dict(os.environ, {"OLLAMA_TIMEOUT_SECONDS":"900", "OLLAMA_NUM_PREDICT":"512"}):
            cfg = self.config()
        self.assertEqual(cfg.OLLAMA_TIMEOUT_SECONDS, 900)
        self.assertEqual(cfg.OLLAMA_NUM_PREDICT, 512)

    def test_rejects_unbounded_or_invalid_budgets(self):
        for values in ({"OLLAMA_TIMEOUT_SECONDS":0}, {"OLLAMA_NUM_PREDICT":-1},
                       {"OLLAMA_TIMEOUT_SECONDS":3601}, {"OLLAMA_NUM_PREDICT":4097}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.config(**values)


class OllamaBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def response(self, reason):
        response = Mock(status_code=200, is_success=True)
        response.json.return_value = {"message":{"content":"Synthetic report"}, "done_reason":reason}
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client
        cfg = settings.model_copy(update={"OLLAMA_TIMEOUT_SECONDS":900, "OLLAMA_NUM_PREDICT":512})
        with patch("app.services.order_analysis_services.settings", cfg), patch(
            "app.services.order_analysis_services.httpx.AsyncClient", return_value=context
        ) as constructor:
            result = await analyze_order_document(
                SimpleNamespace(id="O1", number="TEST", title="Synthetic", issued_on=None),
                SimpleNamespace(description="Training", deadline_on=None, deadline_description="Ongoing",
                                completion_indicator="Report", required_evidence="Report"),
                "synthetic.txt", b"Synthetic training report",
            )
        self.assertEqual(constructor.call_args.kwargs["timeout"].read, 900)
        self.assertEqual(constructor.call_args.kwargs["timeout"].connect, 5)
        options = client.post.await_args.kwargs["json"]["options"]
        self.assertEqual(options["num_predict"], 512)
        self.assertEqual(options["num_ctx"], 8192)
        return result

    async def test_normal_completion_is_not_marked_truncated(self):
        self.assertFalse((await self.response("stop")).output_truncated)

    async def test_length_limit_is_explicit_in_response(self):
        self.assertTrue((await self.response("length")).output_truncated)
