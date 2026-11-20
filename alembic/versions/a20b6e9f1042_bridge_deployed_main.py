"""Bridge deployed e360c96d9546 to backend 5d429ff models.

Candidate for team review. Requires orders, evidences and executions to be empty.
Preserves programs, users, departments, risks, measures and their records.
Use the ROOT migration history; do not combine with backend/alembic migrations.
"""
from alembic import op
import sqlalchemy as sa

revision = "a20b6e9f1042"
down_revision = "e360c96d9546"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Lock before checking so concurrent inserts cannot invalidate the guard.
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.execute("LOCK TABLE orders, evidences, executions IN ACCESS EXCLUSIVE MODE")
    for table in ("orders", "evidences", "executions"):
        count = bind.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one()
        if count:
            raise RuntimeError(
                f"Migration requires empty {table}; found {count} rows. "
                "Stop and prepare a data-preserving backfill."
            )
    op.create_table('order_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=120), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('change_reason', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('size_bytes > 0', name='ck_order_version_nonempty'),
    sa.CheckConstraint('version >= 1', name='ck_order_version_positive'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_id', 'version', name='uq_order_version_number'),
    sa.UniqueConstraint('storage_key')
    )
    op.create_index(op.f('ix_order_versions_order_id'), 'order_versions', ['order_id'], unique=False)
    op.create_table('invalid_order_references',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('measure_id', sa.String(length=8), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=False),
    sa.Column('order_number', sa.String(length=150), nullable=False),
    sa.Column('action', sa.String(length=12), nullable=False),
    sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['measure_id'], ['measures.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invalid_order_references_measure_id'), 'invalid_order_references', ['measure_id'], unique=False)
    op.add_column('executions', sa.Column('id', sa.Integer(), nullable=True))
    op.execute('CREATE SEQUENCE executions_id_seq OWNED BY executions.id')
    op.execute("ALTER TABLE executions ALTER COLUMN id SET DEFAULT nextval('executions_id_seq')")
    op.alter_column('executions', 'id', existing_type=sa.Integer(), nullable=False)
    op.drop_constraint('executions_pkey', 'executions', type_='primary')
    op.create_primary_key('executions_pkey', 'executions', ['id'])
    op.add_column('executions', sa.Column('submitted_department_id', sa.String(length=10), nullable=True))
    op.add_column('executions', sa.Column('order_id', sa.String(length=50), nullable=True))
    op.add_column('executions', sa.Column('order_version_id', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('submitted_sha256', sa.String(length=64), nullable=True))
    op.add_column('executions', sa.Column('document_changed', sa.Boolean(), nullable=False))
    op.add_column('executions', sa.Column('reviewed_by_user_id', sa.Integer(), nullable=True))
    op.add_column('executions', sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('executions', sa.Column('rejection_reason', sa.Text(), nullable=True))
    op.add_column('executions', sa.Column('outcome_status', sa.String(length=20), nullable=True))
    op.alter_column('executions', 'submitted_by_user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.create_index(op.f('ix_executions_measure_id'), 'executions', ['measure_id'], unique=False)
    op.create_index(op.f('ix_executions_order_id'), 'executions', ['order_id'], unique=False)
    op.create_unique_constraint('uq_executions_measure_period_user', 'executions', ['measure_id', 'period', 'submitted_by_user_id'])
    op.create_foreign_key(None, 'executions', 'departments', ['submitted_department_id'], ['id'])
    op.create_foreign_key(None, 'executions', 'orders', ['order_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(None, 'executions', 'order_versions', ['order_version_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(None, 'executions', 'users', ['reviewed_by_user_id'], ['id'])
    op.drop_constraint('ck_execution_status', 'executions', type_='check')
    op.create_check_constraint('ck_execution_status', 'executions',
                               "status IN ('pending', 'approved', 'rejected')")
    op.create_table('order_change_alerts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('execution_id', sa.Integer(), nullable=False),
    sa.Column('measure_id', sa.String(length=8), nullable=False),
    sa.Column('order_id', sa.String(length=50), nullable=False),
    sa.Column('previous_version_id', sa.Integer(), nullable=False),
    sa.Column('new_version_id', sa.Integer(), nullable=False),
    sa.Column('has_approved_execution', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['executions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['measure_id'], ['measures.id'], ),
    sa.ForeignKeyConstraint(['new_version_id'], ['order_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['previous_version_id'], ['order_versions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('execution_id', 'new_version_id', name='uq_order_alert_execution_version')
    )
    op.create_index(op.f('ix_order_change_alerts_measure_id'), 'order_change_alerts', ['measure_id'], unique=False)
    op.create_table('order_change_alert_reads',
    sa.Column('alert_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['alert_id'], ['order_change_alerts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('alert_id', 'user_id')
    )
    op.drop_index(op.f('ix_orders_number'), table_name='orders')
    op.create_unique_constraint('uq_orders_number', 'orders', ['number'])
    op.drop_constraint(op.f('orders_measure_id_fkey'), 'orders', type_='foreignkey')
    op.drop_column('orders', 'measure_id')
    op.drop_table('evidences')


def downgrade():
    raise RuntimeError("Automatic downgrade could lose new submissions and documents. Use a reviewed recovery plan.")
