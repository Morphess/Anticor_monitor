"""Allow separate approvals per executor, preserving existing submissions and alerts.

Revision ID: e45a9067c2f1
Revises: d214e64a0c7b
"""
from alembic import op
import sqlalchemy as sa

revision = 'e45a9067c2f1'
down_revision = 'd214e64a0c7b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    missing = conn.execute(sa.text(
        'SELECT COUNT(*) FROM executions WHERE submitted_by_user_id IS NULL'
    )).scalar_one()
    if missing:
        raise RuntimeError(
            f'Found {missing} executions without executor. Assign an owner to each before migrating; no rows were deleted.'
        )
    # Allocate stable surrogate IDs without discarding old PK values or rows.
    op.add_column('executions', sa.Column('id', sa.Integer(), nullable=True))
    op.execute('CREATE SEQUENCE executions_id_seq')
    op.execute('ALTER SEQUENCE executions_id_seq OWNED BY executions.id')
    op.execute("ALTER TABLE executions ALTER COLUMN id SET DEFAULT nextval('executions_id_seq')")
    op.execute("UPDATE executions SET id = nextval('executions_id_seq') WHERE id IS NULL")
    op.alter_column('executions', 'id', existing_type=sa.Integer(), nullable=False)
    # Foreign-keyed alerts get their proper executor submission ID before changing PK.
    op.add_column('order_change_alerts', sa.Column('execution_id', sa.Integer(), nullable=True))
    op.execute('''UPDATE order_change_alerts a SET execution_id = e.id
                  FROM executions e
                  WHERE a.execution_measure_id=e.measure_id
                    AND a.execution_period=e.period''')
    mismatched = conn.execute(sa.text(
        'SELECT COUNT(*) FROM order_change_alerts WHERE execution_id IS NULL'
    )).scalar_one()
    if mismatched:
        raise RuntimeError(f'{mismatched} alerts have no matching execution. Repair the references first.')
    op.drop_constraint('fk_order_alert_execution', 'order_change_alerts', type_='foreignkey')
    op.drop_constraint('uq_order_alert_execution_version', 'order_change_alerts', type_='unique')
    op.drop_constraint('executions_pkey', 'executions', type_='primary')
    op.create_primary_key('executions_pkey', 'executions', ['id'])
    op.alter_column('executions', 'submitted_by_user_id', existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint('uq_executions_measure_period_user', 'executions',
                                ['measure_id', 'period', 'submitted_by_user_id'])
    op.create_index('ix_executions_measure_id', 'executions', ['measure_id'])
    op.create_foreign_key('fk_order_alert_execution_id', 'order_change_alerts', 'executions',
                          ['execution_id'], ['id'], ondelete='RESTRICT')
    op.create_unique_constraint('uq_order_alert_execution_version', 'order_change_alerts',
                                ['execution_id', 'new_version_id'])
    op.alter_column('order_change_alerts', 'execution_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('order_change_alerts', 'execution_measure_id')
    op.drop_column('order_change_alerts', 'execution_period')


def downgrade() -> None:
    raise NotImplementedError(
        'Multi-executor submissions cannot be merged into one row without data loss. Restore a backup.'
    )
