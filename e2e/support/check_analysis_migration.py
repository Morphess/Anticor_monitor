"""Rehearse the additive migration on populated synthetic a20b6e9f1042 only."""
import os
import runpy
import subprocess
from datetime import date
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
if (os.environ.get("BORDERGROUP_E2E") != "1" or url.host != "db"
        or url.database != "bordergroup_e2e" or url.username != "e2e_user" or url.query):
    raise SystemExit("This migration rehearsal requires the disposable E2E database")


def alembic(*args):
    subprocess.run(["alembic", "-c", "/app/alembic.ini", *args], check=True)


alembic("upgrade", "a20b6e9f1042")
runpy.run_path("/app/e2e/seed.py", run_name="__main__")
from app.database.db_connection import engine, SessionLocal
from app.models.execution import Execution
from app.models.user import User
from app.schemas.execution import ExecutionSubmit
from app.services.execution_services import ExecutionService

# Include a real, pinned submission so the migration is tested with nonempty executions.
with SessionLocal() as db:
    actor = db.scalar(select(User).where(User.login == "pw_executor"))
    today = date.today()
    probe = ExecutionService(db).submit(ExecutionSubmit(measure_id="PW000001",
        period=f"{today.year}-H{1 if today.month < 7 else 2}", order_number="PW-ORDER-1"), actor)
    probe_id = probe.id


def snapshot():
    with engine.connect() as connection:
        result = {}
        for name in inspect(connection).get_table_names():
            if name in {"alembic_version", "execution_analyses"}:
                continue
            quoted = engine.dialect.identifier_preparer.quote(name)
            query = f"SELECT md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text, '[]')) FROM {quoted} AS t"
            result[name] = connection.scalar(text(query))
        return result


alembic("upgrade", "b14e28a0c6f9")
with engine.begin() as connection:
    connection.execute(text("""INSERT INTO execution_analyses
        (execution_id, order_id, order_version_id, submitted_sha256, input_sha256,
         model, file_name, analysis, text_truncated, output_truncated)
        SELECT id, order_id, order_version_id, submitted_sha256, :fingerprint,
               'synthetic-model', 'synthetic.pdf', 'Legacy synthetic report', false, false
        FROM executions WHERE id = :probe"""), {"fingerprint": "a" * 64, "probe": probe_id})
before = snapshot()
alembic("upgrade", "head")
after = snapshot()
if before != {key: after.get(key) for key in before}:
    raise SystemExit("Migration changed existing synthetic records")
alembic("current", "--check-heads")
alembic("check")
from app.services.migrate_analysis_files import main as migrate_files
from app.models.execution_analysis import ExecutionAnalysis
migrate_files()
with SessionLocal() as db:
    report = db.scalar(select(ExecutionAnalysis).where(ExecutionAnalysis.execution_id == probe_id))
    if report.legacy_analysis is not None or report.analysis != "Legacy synthetic report":
        raise SystemExit("Legacy report was not preserved in file storage")
# Remove only the rehearsal submission, leaving the E2E fixture ready for UI submission.
with SessionLocal() as db:
    db.delete(db.get(Execution, probe_id))
    db.commit()
print(f"Analysis migration rehearsal: {len(before)} existing tables preserved, including populated executions")
