"""Separate risk registry from programs; links remain on measures.risk_id.

Revision ID: f713b02d8a21
Revises: e45a9067c2f1
"""
from alembic import op
import sqlalchemy as sa

revision = "f713b02d8a21"
down_revision = "e45a9067c2f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove only an obsolete relation, without deleting risk records.
    # This intentionally preserves risks, risk_measurements and measures.risk_id.
    bind = op.get_bind()
    null_owners = bind.execute(sa.text(
        "SELECT COUNT(*) FROM risks WHERE owner_department_id IS NULL"
    )).scalar_one()
    if null_owners:
        raise RuntimeError(
            f"Є {null_owners} ризиків без owner_department_id. "
            "Спочатку заповніть підрозділ-власник у БД, тоді повторіть міграцію."
        )
    op.drop_constraint("fk_risks_program_id_programs", "risks", type_="foreignkey")
    op.drop_index("ix_risks_program_id", table_name="risks")
    op.drop_column("risks", "program_id")


def downgrade() -> None:
    raise RuntimeError(
        "Неможливо відновити risks.program_id однозначно: один ризик "
        "може використовуватись у кількох програмах. Відновіть резервну копію."
    )
