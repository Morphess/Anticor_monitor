"""create auth users

Revision ID: 842c9b19e77c
Revises: 
Create Date: 2026-11-16 16:25:16.511866

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '842c9b19e77c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_auth_users_login", table_name="auth_users")
    op.drop_table("auth_users")
