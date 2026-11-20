"""Order-based execution approvals (expand-only, keep historical Evidence).

Revision ID: c83a1e9201f3
Revises: b6f41c153c28

This migration intentionally keeps evidences and their legacy alert links.
Do NOT delete historical Evidence until a separate audited backfill exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "c83a1e9201f3"
down_revision = "b6f41c153c28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The previous migration must already be successfully applied.
    # Retain historical reporting columns to avoid losing RF1-RF7 source data.
    op.add_column("executions", sa.Column("outcome_status", sa.String(20), nullable=True))
    op.add_column("executions", sa.Column("order_id", sa.String(50), nullable=True))
    op.add_column("executions", sa.Column("order_version_id", sa.Integer(), nullable=True))
    op.add_column("executions", sa.Column("submitted_sha256", sa.String(64), nullable=True))
    op.add_column("executions", sa.Column("document_changed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("executions", sa.Column("submitted_department_id", sa.String(10), nullable=True))
    op.add_column("executions", sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("executions", sa.Column("reviewed_at", sa.DateTime(timezone=False), nullable=True))
    op.add_column("executions", sa.Column("rejection_reason", sa.Text(), nullable=True))

    op.create_index("ix_executions_order_id", "executions", ["order_id"])
    op.create_foreign_key("fk_executions_order", "executions", "orders", ["order_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_executions_order_version", "executions", "order_versions", ["order_version_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_executions_department", "executions", "departments", ["submitted_department_id"], ["id"])
    op.create_foreign_key("fk_executions_reviewer", "executions", "users", ["reviewed_by_user_id"], ["id"])

    # Keep old self-reported execution state in a separate reporting column.
    op.execute("UPDATE executions SET outcome_status = status")
    op.drop_constraint("ck_execution_status", "executions", type_="check")
    op.execute("""UPDATE executions SET status = CASE
               WHEN approved_by_coordinator THEN 'approved' ELSE 'pending' END""")
    op.create_check_constraint("ck_execution_status", "executions",
                               "status IN ('pending', 'approved', 'rejected')")

    # One alert either links to an archived Evidence or to a new execution.
    op.alter_column("order_change_alerts", "evidence_id", existing_type=sa.String(12), nullable=True)
    op.add_column("order_change_alerts", sa.Column("execution_measure_id", sa.String(8), nullable=True))
    op.add_column("order_change_alerts", sa.Column("execution_period", sa.String(20), nullable=True))
    op.create_foreign_key("fk_order_alert_execution", "order_change_alerts", "executions",
                          ["execution_measure_id", "execution_period"], ["measure_id", "period"],
                          ondelete="RESTRICT")
    op.create_unique_constraint("uq_order_alert_execution_version", "order_change_alerts",
                                ["execution_measure_id", "execution_period", "new_version_id"])
    op.create_check_constraint("ck_order_alert_target", "order_change_alerts", """
       (evidence_id IS NOT NULL AND execution_measure_id IS NULL AND execution_period IS NULL)
       OR
       (evidence_id IS NULL AND execution_measure_id IS NOT NULL AND execution_period IS NOT NULL)
    """)


def downgrade() -> None:
    # Do not silently discard submissions/reviews/version alerts after rollout.
    bind = op.get_bind()
    affected = bind.execute(sa.text("""
        SELECT COUNT(*) FROM executions
        WHERE order_id IS NOT NULL OR order_version_id IS NOT NULL
           OR status = 'rejected' OR reviewed_by_user_id IS NOT NULL
    """)).scalar_one()
    alerts = bind.execute(sa.text("""
        SELECT COUNT(*) FROM order_change_alerts WHERE execution_measure_id IS NOT NULL
    """)).scalar_one()
    if affected or alerts:
        raise RuntimeError("Rollback would lose new workflow history. Restore backup instead.")
    op.drop_constraint("ck_order_alert_target", "order_change_alerts", type_="check")
    op.drop_constraint("uq_order_alert_execution_version", "order_change_alerts", type_="unique")
    op.drop_constraint("fk_order_alert_execution", "order_change_alerts", type_="foreignkey")
    op.drop_column("order_change_alerts", "execution_period")
    op.drop_column("order_change_alerts", "execution_measure_id")
    op.alter_column("order_change_alerts", "evidence_id", existing_type=sa.String(12), nullable=False)
    op.drop_constraint("ck_execution_status", "executions", type_="check")
    op.execute("UPDATE executions SET status = outcome_status")
    op.create_check_constraint("ck_execution_status", "executions", "status IN ('completed', 'partial', 'not_completed', 'in_progress', 'not_started')")
    for name in ("fk_executions_reviewer", "fk_executions_department", "fk_executions_order_version", "fk_executions_order"):
        op.drop_constraint(name, "executions", type_="foreignkey")
    op.drop_index("ix_executions_order_id", "executions")
    for column in ("rejection_reason", "reviewed_at", "reviewed_by_user_id", "submitted_department_id",
                   "document_changed", "submitted_sha256", "order_version_id", "order_id", "outcome_status"):
        op.drop_column("executions", column)
