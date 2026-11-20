"""Add audited risk reassessment history (does not rewrite old risks).

Revision ID: ab61f9482c20
Revises: f713b02d8a21
"""
from alembic import op
import sqlalchemy as sa

revision = "ab61f9482c20"
down_revision = "f713b02d8a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("risk_id", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=15), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("assessed_on", sa.Date(), nullable=False),
        sa.Column("probability_score", sa.Integer(), nullable=False),
        sa.Column("impact_score", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("measurement_on", sa.Date(), nullable=True),
        sa.Column("measurement_value", sa.Numeric(14, 3), nullable=True),
        sa.Column("measurement_source", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("probability_score BETWEEN 1 AND 4", name="ck_ra_probability"),
        sa.CheckConstraint("impact_score BETWEEN 1 AND 4", name="ck_ra_impact"),
        sa.CheckConstraint("score = probability_score * impact_score", name="ck_ra_score"),
        sa.CheckConstraint("level IN ('low', 'medium', 'high', 'critical')", name="ck_ra_level"),
        sa.CheckConstraint("kind IN ('baseline', 'reassessment')", name="ck_ra_kind"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'rejected')", name="ck_ra_status"),
        sa.CheckConstraint(
            "(kind = 'baseline' AND status = 'approved' AND measurement_on IS NULL) "
            "OR (kind = 'reassessment' AND measurement_on IS NOT NULL)",
            name="ck_ra_kind_measurement",
        ),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["risk_id", "measurement_on"],
            ["risk_measurements.risk_id", "risk_measurements.measured_on"],
            ondelete="RESTRICT", name="fk_ra_measurement",
        ),
    )
    op.create_index("ix_ra_risk_id_approved", "risk_assessments", ["risk_id", "status", "id"])
    op.create_index(
        "ux_ra_baseline_per_risk", "risk_assessments", ["risk_id"], unique=True,
        postgresql_where=sa.text("kind = 'baseline'"),
    )
    op.create_index(
        "ux_ra_one_draft_per_risk", "risk_assessments", ["risk_id"], unique=True,
        postgresql_where=sa.text("kind = 'reassessment' AND status = 'draft'"),
    )

    # Завершені оцінки і початкова оцінка є незмінними навіть для прямого SQL.
    # Чернетка може лише один раз перейти в approved/rejected без підміни чисел.
    op.execute("""
        CREATE FUNCTION protect_final_risk_assessment() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Risk assessments cannot be deleted';
            END IF;
            IF OLD.status <> 'draft' THEN
                RAISE EXCEPTION 'Final risk assessment is immutable';
            END IF;
            IF NEW.status NOT IN ('approved', 'rejected') THEN
                RAISE EXCEPTION 'Only final transition is allowed';
            END IF;
            IF NEW.risk_id IS DISTINCT FROM OLD.risk_id
               OR NEW.kind IS DISTINCT FROM OLD.kind
               OR NEW.assessed_on IS DISTINCT FROM OLD.assessed_on
               OR NEW.probability_score IS DISTINCT FROM OLD.probability_score
               OR NEW.impact_score IS DISTINCT FROM OLD.impact_score
               OR NEW.score IS DISTINCT FROM OLD.score
               OR NEW.level IS DISTINCT FROM OLD.level
               OR NEW.measurement_on IS DISTINCT FROM OLD.measurement_on
               OR NEW.measurement_value IS DISTINCT FROM OLD.measurement_value
               OR NEW.measurement_source IS DISTINCT FROM OLD.measurement_source
               OR NEW.justification IS DISTINCT FROM OLD.justification
               OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN
                RAISE EXCEPTION 'Assessment evidence cannot be altered';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER tg_protect_final_risk_assessment
        BEFORE UPDATE OR DELETE ON risk_assessments
        FOR EACH ROW EXECUTE FUNCTION protect_final_risk_assessment();
    """)


def downgrade() -> None:
    # Втрата історії переоцінок неприпустима без резервної копії.
    raise RuntimeError("Відкат видалить журнал переоцінок. Відновіть резервну копію.")
