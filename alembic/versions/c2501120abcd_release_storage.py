"""File-backed AI reports and the backend_v2 risk assessment schema."""
from alembic import op
import sqlalchemy as sa
import importlib.util
from pathlib import Path
revision = "c2501120abcd"
down_revision = "b14e28a0c6f9"
branch_labels = depends_on = None

def upgrade():
    op.alter_column("execution_analyses", "analysis", existing_type=sa.Text(), nullable=True)
    op.add_column("execution_analyses", sa.Column("report_key", sa.String(64)))
    op.add_column("execution_analyses", sa.Column("report_sha256", sa.String(64)))
    spec = importlib.util.spec_from_file_location("risk_history", Path(__file__).resolve().parents[1] / "risk_history_impl.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.upgrade()

def downgrade():
    raise RuntimeError("Restore a reviewed DB/files backup; report history must not be lost")
