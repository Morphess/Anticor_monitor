"""Ensure the active workflow roles exist on fresh and existing installations."""
from alembic import op
import sqlalchemy as sa

revision = "d2511200abcd"
down_revision = "c2501120abcd"
branch_labels = depends_on = None


def upgrade():
    for code, name in (
        ("ADMIN", "Адміністратор"),
        ("MAIN_KOORD", "Головний координатор"),
        ("KOORD", "Координатор"),
        ("VYK", "Виконавець"),
        ("KER", "Керівник"),
    ):
        op.get_bind().execute(sa.text(
            "INSERT INTO roles (id, name) VALUES (:id, :name) ON CONFLICT (id) DO NOTHING"
        ), {"id": code, "name": name})


def downgrade():
    # Roles may already be assigned to users; keep them on rollback.
    pass
