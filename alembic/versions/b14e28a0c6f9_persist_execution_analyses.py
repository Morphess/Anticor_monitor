"""Persist completed execution analyses without modifying existing records."""
from alembic import op
import sqlalchemy as sa

revision = "b14e28a0c6f9"
down_revision = "a20b6e9f1042"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("execution_analyses",
        sa.Column("analysis_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.Integer(), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.String(50), sa.ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("order_version_id", sa.Integer(), sa.ForeignKey("order_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_sha256", sa.String(64), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=False),
        sa.Column("text_truncated", sa.Boolean(), nullable=False),
        sa.Column("output_truncated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
    )
    op.create_index("ix_execution_analyses_lookup", "execution_analyses",
                    ["execution_id", "order_version_id", "submitted_sha256", "input_sha256", "analysis_id"])


def downgrade():
    raise RuntimeError("Export saved AI reports and agree a recovery plan before removing this table")
