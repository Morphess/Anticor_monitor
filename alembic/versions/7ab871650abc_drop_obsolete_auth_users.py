"""drop obsolete auth users

Revision ID: 7ab871650abc
Revises: 2dcc7d9ed549
Create Date: 2026-11-17 13:34:00.926047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ab871650abc'
down_revision: Union[str, Sequence[str], None] = '2dcc7d9ed549'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("auth_users")


def downgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_auth_users_login",
        "auth_users",
        ["login"],
        unique=True,
    )
