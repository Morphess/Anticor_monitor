import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("APP_NAME", "Test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "synthetic-test-key-at-least-32-bytes")
from app.services.execution_analysis_services import analysis_input
from app.services.execution_services import ExecutionError
from app.services.order_analysis_services import MAX_DOCUMENT_BYTES, OrderAnalysisError


class ExecutionAnalysisStorageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/"pinned.pdf"
        self.content = b"%PDF-synthetic-test"
        self.path.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.row = SimpleNamespace(measure_id="M01", order_id="O01", submitted_sha256=self.digest)
        self.version = SimpleNamespace(id=3, size_bytes=len(self.content), sha256=self.digest, original_filename="original.pdf")
        self.db = Mock()
        self.db.get.return_value = SimpleNamespace(id="O01")
        self.actor = SimpleNamespace(id=7, role_id="KOORD")
        patcher = patch("app.services.execution_analysis_services.ExecutionService")
        self.svc = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.svc.get.return_value = self.row
        self.svc.get_document.return_value = (self.path, self.version)
        patcher = patch("app.services.execution_analysis_services.require_visible_measure", return_value=SimpleNamespace(id="M01"))
        self.visible = patcher.start()
        self.addCleanup(patcher.stop)

    def read(self):
        return analysis_input(self.db, self.actor, 11)

    def test_reads_exact_verified_pinned_bytes(self):
        result = self.read()
        self.assertEqual(result[2:], ("original.pdf", self.content, 3, self.digest))
        self.visible.assert_called_once_with(self.db, self.actor, "M01")
        self.svc.require_read_access.assert_called_once_with(self.row, self.actor)
        self.svc.get_document.assert_called_once_with(self.row, self.actor, which="submitted")

    def test_rejects_changed_bytes_after_storage_verification(self):
        self.path.write_bytes(b"modified")
        with self.assertRaises(ExecutionError) as ctx:
            self.read()
        self.assertEqual(ctx.exception.status_code, 409)

    def test_rejects_pinned_hash_mismatch(self):
        self.row.submitted_sha256 = "b"*64
        with self.assertRaises(ExecutionError):
            self.read()

    def test_rejects_oversized_document(self):
        self.version.size_bytes = MAX_DOCUMENT_BYTES+1
        with self.assertRaises(OrderAnalysisError) as ctx:
            self.read()
        self.assertEqual(ctx.exception.status_code, 413)
