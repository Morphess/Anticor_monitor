"""add program workflow

Revision ID: e360c96d9546
Revises: c8e4a2d6f1b7
"""

from alembic import op
import sqlalchemy as sa


revision = "e360c96d9546"
down_revision = "c8e4a2d6f1b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "departments",
        sa.Column("parent_id", sa.String(10), nullable=True),
    )
    op.create_foreign_key(
        "fk_departments_parent_id",
        "departments",
        "departments",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])

    op.add_column(
        "programs",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_programs_created_by_user_id",
        "programs",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_programs_created_by_user_id",
        "programs",
        ["created_by_user_id"],
    )

    op.create_table(
        "program_departments",
        sa.Column(
            "program_id",
            sa.String(50),
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "department_id",
            sa.String(10),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "sent_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_program_departments_department_id",
        "program_departments",
        ["department_id"],
    )

    op.create_table(
        "measure_assignments",
        sa.Column(
            "measure_id",
            sa.String(8),
            sa.ForeignKey("measures.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "department_id",
            sa.String(10),
            sa.ForeignKey("departments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_measure_assignments_user_id",
        "measure_assignments",
        ["user_id"],
    )
    op.create_index(
        "ix_measure_assignments_department_id",
        "measure_assignments",
        ["department_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_measure_assignments_department_id",
        table_name="measure_assignments",
    )
    op.drop_index("ix_measure_assignments_user_id", table_name="measure_assignments")
    op.drop_table("measure_assignments")

    op.drop_index(
        "ix_program_departments_department_id",
        table_name="program_departments",
    )
    op.drop_table("program_departments")

    op.drop_index("ix_programs_created_by_user_id", table_name="programs")
    op.drop_constraint(
        "fk_programs_created_by_user_id",
        "programs",
        type_="foreignkey",
    )
    op.drop_column("programs", "created_by_user_id")

    op.drop_index("ix_departments_parent_id", table_name="departments")
    op.drop_constraint(
        "fk_departments_parent_id",
        "departments",
        type_="foreignkey",
    )
    op.drop_column("departments", "parent_id")