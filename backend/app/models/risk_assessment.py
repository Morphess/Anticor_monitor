"""Незмінний журнал первинної оцінки та переоцінок корупційного ризику."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, String, Text, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint("probability_score BETWEEN 1 AND 4", name="ck_ra_probability"),
        CheckConstraint("impact_score BETWEEN 1 AND 4", name="ck_ra_impact"),
        CheckConstraint("score = probability_score * impact_score", name="ck_ra_score"),
        CheckConstraint("level IN ('low', 'medium', 'high', 'critical')", name="ck_ra_level"),
        CheckConstraint("kind IN ('baseline', 'reassessment')", name="ck_ra_kind"),
        CheckConstraint("status IN ('draft', 'approved', 'rejected')", name="ck_ra_status"),
        CheckConstraint(
            "(kind = 'baseline' AND status = 'approved' AND measurement_on IS NULL) "
            "OR (kind = 'reassessment' AND measurement_on IS NOT NULL)",
            name="ck_ra_kind_measurement",
        ),
        ForeignKeyConstraint(
            ["risk_id", "measurement_on"],
            ["risk_measurements.risk_id", "risk_measurements.measured_on"],
            ondelete="RESTRICT", name="fk_ra_measurement",
        ),
        Index("ix_ra_risk_id_approved", "risk_id", "status", "id"),
        Index(
            "ux_ra_baseline_per_risk", "risk_id", unique=True,
            postgresql_where=text("kind = 'baseline'"),
            sqlite_where=text("kind = 'baseline'"),
        ),
        Index(
            "ux_ra_one_draft_per_risk", "risk_id", unique=True,
            postgresql_where=text("kind = 'reassessment' AND status = 'draft'"),
            sqlite_where=text("kind = 'reassessment' AND status = 'draft'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("risks.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(15), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    assessed_on: Mapped[date] = mapped_column(Date, nullable=False)
    probability_score: Mapped[int] = mapped_column(Integer, nullable=False)
    impact_score: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    measurement_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    measurement_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    measurement_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
