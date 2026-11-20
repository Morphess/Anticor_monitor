"""Run after upgrade head, with the same persistent report volume as API."""
from sqlalchemy import select
from app.database.db_connection import SessionLocal
from app.models.execution_analysis import ExecutionAnalysis
from app.services.analysis_report_storage import write_report, read_report


def main():
    count = 0
    with SessionLocal() as db:
        while True:
            row = db.scalar(select(ExecutionAnalysis).where(
                ExecutionAnalysis.legacy_analysis.is_not(None)
            ).with_for_update().limit(1))
            if row is None:
                break
            key, checksum = write_report(row.legacy_analysis)
            if read_report(key, checksum) != row.legacy_analysis:
                raise RuntimeError('Report copy failed verification')
            row.report_key, row.report_sha256 = key, checksum
            row.legacy_analysis = None
            db.commit()
            count += 1
    print(f'Migrated AI report bodies to files: {count}')

if __name__ == '__main__':
    main()
