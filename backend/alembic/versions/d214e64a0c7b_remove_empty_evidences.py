"""Remove empty legacy evidences after execution workflow rollout.

Revision ID: d214e64a0c7b
Revises: c83a1e9201f3

Requires evidences and legacy evidence alerts to be empty. Only use after
verified backup and upgrade to the preceding workflow migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "d214e64a0c7b"
down_revision = "c83a1e9201f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Fail closed; never destroy legacy rows or references by accident.
    count = bind.execute(sa.text("SELECT count(*) FROM evidences")).scalar_one()
    if count:
        raise RuntimeError(f"Cannot drop evidences: {count} rows still exist. Backup and migrate them first.")
    legacy_alerts = bind.execute(sa.text(
        "SELECT count(*) FROM order_change_alerts WHERE evidence_id IS NOT NULL"
    )).scalar_one()
    if legacy_alerts:
        raise RuntimeError(f"Cannot remove evidence link: {legacy_alerts} alerts still reference it.")
    incomplete = bind.execute(sa.text(
        "SELECT count(*) FROM order_change_alerts "
        "WHERE execution_measure_id IS NULL OR execution_period IS NULL"
    )).scalar_one()
    if incomplete:
        raise RuntimeError(f"Cannot require execution links: {incomplete} alerts have no execution.")

    op.drop_constraint("ck_order_alert_target", "order_change_alerts", type_="check")
    op.drop_constraint("uq_order_alert_evidence_version", "order_change_alerts", type_="unique")
    # Name comes from the originally unnamed FK in migration b6f41c153c28.
    op.drop_constraint("order_change_alerts_evidence_id_fkey", "order_change_alerts", type_="foreignkey")
    op.drop_column("order_change_alerts", "evidence_id")
    op.alter_column("order_change_alerts", "execution_measure_id", existing_type=sa.String(8), nullable=False)
    op.alter_column("order_change_alerts", "execution_period", existing_type=sa.String(20), nullable=False)
    op.drop_table("evidences")


def downgrade() -> None:
    raise NotImplementedError("Recreating old Evidence data links needs a dedicated audited migration or a backup.")
