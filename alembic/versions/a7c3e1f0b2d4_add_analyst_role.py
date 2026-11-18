"""add analyst role

Revision ID: a7c3e1f0b2d4
Revises: 7ab871650abc
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a7c3e1f0b2d4"
down_revision: Union[str, Sequence[str], None] = "7ab871650abc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Роль «Аналітик» — перегляд програм і аналітики без права змін.
    op.execute(
        "INSERT INTO roles (id, name) SELECT 'ANAL', 'Аналітик' "
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE id = 'ANAL')"
    )


def downgrade() -> None:
    # Роль не видаляємо: на неї можуть посилатися користувачі.
    pass
