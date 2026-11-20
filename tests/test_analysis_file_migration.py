import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from app.services.migrate_analysis_files import main

class FileMigrationTests(unittest.TestCase):
    def test_clears_legacy_text_only_after_verified_file(self):
        row=SimpleNamespace(legacy_analysis='old report',report_key=None,report_sha256=None)
        db=MagicMock();db.scalar.side_effect=[row,None]
        with patch('app.services.migrate_analysis_files.SessionLocal') as sessions, \
             patch('app.services.migrate_analysis_files.write_report',return_value=('key','sha')), \
             patch('app.services.migrate_analysis_files.read_report',return_value='old report'):
            sessions.return_value.__enter__.return_value=db
            main()
        self.assertIsNone(row.legacy_analysis)
        self.assertEqual(row.report_key,'key')
        db.commit.assert_called_once()

    def test_does_not_clear_legacy_text_on_copy_failure(self):
        row=SimpleNamespace(legacy_analysis='old report')
        db=MagicMock();db.scalar.return_value=row
        with patch('app.services.migrate_analysis_files.SessionLocal') as sessions, \
             patch('app.services.migrate_analysis_files.write_report',side_effect=OSError('disk full')):
            sessions.return_value.__enter__.return_value=db
            with self.assertRaises(OSError):main()
        self.assertEqual(row.legacy_analysis,'old report')
        db.commit.assert_not_called()
