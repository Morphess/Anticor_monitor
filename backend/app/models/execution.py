"""Виконання одного заходу за конкретний звітний період."""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Фактичний стан одного заходу в конкретному звітному періоді.
class Execution(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "executions"
    # Правила цілісності БД: унікальність і перевірки значень.
    __table_args__ = (
        CheckConstraint(
            # Не даємо зберегти невідомі статуси виконання.
            "status IN ('completed', 'partial', 'not_completed', 'in_progress', 'not_started')",
            name="ck_execution_status",
        ),
    )

    # ID заходу; разом із period утворює складений первинний ключ.
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), primary_key=True)
    # Звітний період, наприклад 2026-H1; разом із measure_id є PK.
    period: Mapped[str] = mapped_column(String(20), primary_key=True)  # 2026-H1
    # Внутрішній технічний код стану: completed, partial тощо.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Людинозрозумілий український підпис статусу з джерела.
    status_label: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # original UA wording
    # Фактична дата завершення заходу, якщо застосовна.
    completed_on: Mapped[date | None] = mapped_column(Date)
    # Що реально зроблено або чому захід не виконаний.
    result_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Фактичне числове значення показника виконання; може бути NULL.
    indicator_actual: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    # Реальний користувач, який вніс звіт у застосунку.
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Дата й час подання інформації.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    # Чи погодив звіт координатор: True або False.
    approved_by_coordinator: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ORM-доступ до заходу, якого стосується результат.
    measure: Mapped["Measure"] = relationship("Measure", back_populates="executions")
    # ORM-доступ до реального подавача.
    submitted_by_user: Mapped["User | None"] = relationship("User")
