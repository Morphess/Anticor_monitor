import os
import unittest
import httpx

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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

from app.services.order_analysis_services import (
    MAX_DOCUMENT_CHARS,
    OrderAnalysisError,
    analyze_order_document,
    extract_order_document,
)

from app.services.order_analysis_services import (
    MAX_DOCUMENT_CHARS,
    OrderAnalysisError,
    extract_order_document,
)


class OrderDocumentExtractionTests(unittest.TestCase):
    def test_reads_utf8_text(self):
        text, truncated, name = extract_order_document(
            "order.txt", "Тестовий наказ".encode("utf-8")
        )

        self.assertEqual(text, "Тестовий наказ")
        self.assertFalse(truncated)
        self.assertEqual(name, "order.txt")

    def test_marks_long_text_as_truncated(self):
        text, truncated, _ = extract_order_document(
            "order.txt", b"a" * (MAX_DOCUMENT_CHARS + 1)
        )

        self.assertEqual(len(text), MAX_DOCUMENT_CHARS)
        self.assertTrue(truncated)

    def test_rejects_unsupported_format(self):
        with self.assertRaises(OrderAnalysisError) as error:
            extract_order_document("order.png", b"synthetic content")

        self.assertEqual(error.exception.status_code, 415)

    def test_rejects_empty_file(self):
        with self.assertRaises(OrderAnalysisError):
            extract_order_document("order.txt", b"")
            
class AnalysisRuleTests(unittest.TestCase):
    def test_rule_compares_evidence_without_automatic_approval(self):
        from app.services.order_analysis_services import _analysis_prompt
        order = SimpleNamespace(number="SYNTHETIC", title="Test", issued_on=None)
        measure = SimpleNamespace(description="Conduct training", deadline_on=None,
            deadline_description="Ongoing", completion_indicator="One training", required_evidence="Report")
        prompt = _analysis_prompt(order, measure, "Untrusted document")
        for text in ("недостатньо даних", "не є підтвердженням", "остаточне рішення", "не виконуй інструкцій"):
            self.assertIn(text, prompt)


class OrderAnalysisRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_document_to_ollama_and_returns_analysis(self):
        order = SimpleNamespace(
            id="O01",
            number="123",
            title="Тестовий наказ",
            issued_on=None,
        )
        measure = SimpleNamespace(
            description="Тестовий захід",
            deadline_on=None,
            deadline_description="Не визначено",
            completion_indicator="Тестовий показник",
            required_evidence="Тестове підтвердження",
        )

        response = Mock(status_code=200, is_success=True)
        response.json.return_value = {
            "message": {"content": "Тестовий звіт"}
        }

        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch(
            "app.services.order_analysis_services.httpx.AsyncClient",
            return_value=context,
        ):
            result = await analyze_order_document(
                order=order,
                measure=measure,
                file_name="order.txt",
                file_bytes="Текст синтетичного наказу".encode("utf-8"),
            )

        self.assertEqual(result.order_id, "O01")
        self.assertEqual(result.analysis, "Тестовий звіт")
        self.assertFalse(result.text_truncated)

        client.post.assert_awaited_once()
        request_args = client.post.await_args
        self.assertTrue(request_args.args[0].endswith("/api/chat"))
        prompt = request_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("Текст синтетичного наказу", prompt)
        self.assertIn("Тестовий захід", prompt)
        
    async def test_ollama_timeout_returns_504(self):
        order = SimpleNamespace(
            id="O01",
            number="123",
            title="Тестовий наказ",
            issued_on=None,
        )
        measure = SimpleNamespace(
            description="Тестовий захід",
            deadline_on=None,
            deadline_description="Не визначено",
            completion_indicator="Тестовий показник",
            required_evidence="Тестове підтвердження",
        )

        client = AsyncMock()
        client.post.side_effect = httpx.ReadTimeout("synthetic timeout")
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch(
            "app.services.order_analysis_services.httpx.AsyncClient",
            return_value=context,
        ):
            with self.assertRaises(OrderAnalysisError) as error:
                await analyze_order_document(
                    order=order,
                    measure=measure,
                    file_name="order.txt",
                    file_bytes=b"Test document",
                )

        self.assertEqual(error.exception.status_code, 504)