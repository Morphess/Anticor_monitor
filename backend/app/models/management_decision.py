from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


# Рішення керівника за рекомендацією системи (сигналом правила RF*).
# Один сигнал за звітний період — одне рішення.
class ManagementDecision(Base):
    __tablename__ = "management_decisions"
    __table_args__ = (
        UniqueConstraint("signal_key", "period", name="uq_decision_signal_period"),
        CheckConstraint("decision IN ('assign', 'dismiss')", name="ck_decision_kind"),
        # Доручення потребує відповідального й строку, відхилення — причини.
        CheckConstraint(
            "decision <> 'assign' OR (responsible_department_id IS NOT NULL AND due_on IS NOT NULL)",
            name="ck_decision_assign_fields",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Стабільний ключ сигналу: код правила + об'єкт, наприклад RF1:Z-01.
    signal_key: Mapped[str] = mapped_column(String(60), nullable=False)
    # Звітний період, у якому ухвалено рішення (2026-H2).
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    # Код правила: RF1, RF2, ...
    rule_code: Mapped[str] = mapped_column(String(10), nullable=False)
    # Що саме побачив керівник у момент рішення (знімок, бо сигнал згодом може зникнути).
    signal_title: Mapped[str] = mapped_column(Text, nullable=False)
    object_label: Mapped[str] = mapped_column(Text, nullable=False)

    # assign — доручити; dismiss — відхилити з причиною.
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    responsible_department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"))
    due_on: Mapped[date | None] = mapped_column(Date)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")

    decided_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    responsible_department: Mapped["Department | None"] = relationship("Department")
    decided_by: Mapped["User"] = relationship("User")
