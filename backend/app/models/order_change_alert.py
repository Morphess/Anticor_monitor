"""Повідомлення про зміну наказу, який уже використано в Evidence."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class OrderChangeAlert(Base):
    __tablename__ = "order_change_alerts"
    __table_args__ = (
        UniqueConstraint("evidence_id", "new_version_id", name="uq_order_alert_evidence_version"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidences.id", ondelete="RESTRICT"), nullable=False)
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    previous_version_id: Mapped[int] = mapped_column(ForeignKey("order_versions.id", ondelete="RESTRICT"), nullable=False)
    new_version_id: Mapped[int] = mapped_column(ForeignKey("order_versions.id", ondelete="RESTRICT"), nullable=False)
    has_approved_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrderChangeAlertRead(Base):
    """Ознайомлення з повідомленням окремим координатором (без втрати для інших)."""
    __tablename__ = "order_change_alert_reads"
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("order_change_alerts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
