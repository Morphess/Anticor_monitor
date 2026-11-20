import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.services.analysis_report_storage import write_report, read_report, report_path

class ReportFileTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env=patch.dict(os.environ,{'REPORT_EXPORT_DIR':tmp.name})
        env.start();self.addCleanup(env.stop)

    def test_private_report_and_integrity(self):
        key,sha=write_report('Синтетичний висновок <script>alert(1)</script>')
        self.assertIn('Синтетичний',read_report(key,sha))
        self.assertEqual(report_path(key).stat().st_mode & 0o777,0o600)
        report_path(key).write_text('modified')
        with self.assertRaises(OSError):read_report(key,sha)

    def test_traversal_and_symlink_rejected(self):
        for key in ('../secret','/etc/passwd','a.txt'):
            with self.assertRaises(OSError):report_path(key)
        key,sha=write_report('synthetic')
        p=report_path(key);p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises(OSError):read_report(key,sha)
