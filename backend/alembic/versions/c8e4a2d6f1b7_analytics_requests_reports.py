"""analytics requests and reports

Revision ID: c8e4a2d6f1b7
Revises: b5d2f8c1a9e3
Create Date: 2026-11-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c8e4a2d6f1b7"
down_revision: Union[str, Sequence[str], None] = "b5d2f8c1a9e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("program_id", sa.String(length=50), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("analyst_user_id", sa.Integer(), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=False), nullable=True),
        sa.CheckConstraint("status IN ('new', 'in_progress', 'answered')", name="ck_analytics_request_status"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["analyst_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "analytics_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("program_id", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("findings", sa.Text(), nullable=False),
        sa.Column("proposals", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["analytics_requests.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_analytics_report_request"),
    )


def downgrade() -> None:
    op.drop_table("analytics_reports")
    op.drop_table("analytics_requests")
