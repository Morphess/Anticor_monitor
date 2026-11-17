"""management decisions and manager role

Revision ID: b5d2f8c1a9e3
Revises: a7c3e1f0b2d4
Create Date: 2026-11-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b5d2f8c1a9e3"
down_revision: Union[str, Sequence[str], None] = "a7c3e1f0b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Роль «Керівник» — панелі та рішення за рекомендаціями.
    op.execute(
        "INSERT INTO roles (id, name) SELECT 'KER', 'Керівник' "
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE id = 'KER')"
    )
    op.create_table(
        "management_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_key", sa.String(length=60), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("rule_code", sa.String(length=10), nullable=False),
        sa.Column("signal_title", sa.Text(), nullable=False),
        sa.Column("object_label", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("responsible_department_id", sa.String(length=10), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=False), nullable=False),
        sa.CheckConstraint("decision IN ('assign', 'dismiss')", name="ck_decision_kind"),
        sa.CheckConstraint(
            "decision <> 'assign' OR (responsible_department_id IS NOT NULL AND due_on IS NOT NULL)",
            name="ck_decision_assign_fields",
        ),
        sa.ForeignKeyConstraint(["responsible_department_id"], ["departments.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_key", "period", name="uq_decision_signal_period"),
    )


def downgrade() -> None:
    op.drop_table("management_decisions")
    # Роль не видаляємо: на неї можуть посилатися користувачі.
