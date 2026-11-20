"""Часовий ряд індикаторів ризику (source: vymiriuvannia_indykatoriv)."""

from __future__ import annotations
from datetime import date
from decimal import Decimal
from sqlalchemy import Date, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Окреме значення індикатора одного ризику на одну дату.
class RiskMeasurement(Base):
    __tablename__ = "risk_measurements"

    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id"), primary_key=True)
    measured_on: Mapped[date] = mapped_column(Date, primary_key=True)
    # Числовий результат вимірювання індикатора.
    value: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    # Джерело показника (звідки отримано дані).
    source: Mapped[str] = mapped_column(Text, nullable=False)

    risk: Mapped["Risk"] = relationship("Risk", back_populates="measurements")
