"""Order-change alerts must identify the individual executor's submission."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class OrderChangeAlert(Base):
    __tablename__ = 'order_change_alerts'
    __table_args__ = (
        UniqueConstraint('execution_id', 'new_version_id', name='uq_order_alert_execution_version'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey('executions.id', ondelete='RESTRICT'), nullable=False)
    measure_id: Mapped[str] = mapped_column(ForeignKey('measures.id'), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), nullable=False)
    previous_version_id: Mapped[int] = mapped_column(ForeignKey('order_versions.id', ondelete='RESTRICT'), nullable=False)
    new_version_id: Mapped[int] = mapped_column(ForeignKey('order_versions.id', ondelete='RESTRICT'), nullable=False)
    has_approved_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OrderChangeAlertRead(Base):
    __tablename__ = 'order_change_alert_reads'
    alert_id: Mapped[int] = mapped_column(ForeignKey('order_change_alerts.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
