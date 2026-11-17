"""Make risks independent

Revision ID: 2dcc7d9ed549
Revises: dfd4fb0168b9
Create Date: 2026-11-17 09:37:46.458594
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2dcc7d9ed549"
down_revision: Union[str, Sequence[str], None] = "dfd4fb0168b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Робимо ризики незалежними від програм."""

    # Прибираємо зовнішній ключ risks -> programs.
    op.drop_constraint(
        "risks_program_id_fkey",
        "risks",
        type_="foreignkey",
    )

    # Видаляємо program_id з таблиці risks.
    # Інші поля й записи ризиків зберігаються.
    op.drop_column(
        "risks",
        "program_id",
    )


def downgrade() -> None:
    """
    Автоматичний відкат не підтримується.

    Після видалення program_id неможливо надійно
    визначити, до якої програми раніше належав ризик.

    Для повернення старої структури потрібні
    резервна копія або окрема міграція даних.
    """

    raise NotImplementedError(
        "Автоматичне відновлення risks.program_id " "неможливе без початкових даних."
    )
