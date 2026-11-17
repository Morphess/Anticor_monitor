"""Часовий ряд індикаторів ризику (source: vymiriuvannia_indykatoriv)."""

from __future__ import annotations
from datetime import date
from decimal import Decimal
from sqlalchemy import Date, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Окреме значення індикатора одного ризику на одну дату.
class RiskMeasurement(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "risk_measurements"

    # Код ризику, частина складеного первинного ключа.
    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id"), primary_key=True)
    # Дата, коли виміряли показник; друга частина PK.
    measured_on: Mapped[date] = mapped_column(Date, primary_key=True)
    # Числовий результат вимірювання індикатора.
    value: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    # Джерело показника (звідки отримано дані).
    source: Mapped[str] = mapped_column(Text, nullable=False)

    # ORM-доступ до ризику.
    risk: Mapped["Risk"] = relationship("Risk", back_populates="measurements")
