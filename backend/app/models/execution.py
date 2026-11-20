"""Each assigned executor owns an independent submission for each measure/period."""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class Execution(Base):
    __tablename__ = 'executions'
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='ck_execution_status'),
        UniqueConstraint('measure_id', 'period', 'submitted_by_user_id', name='uq_executions_measure_period_user'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    measure_id: Mapped[str] = mapped_column(ForeignKey('measures.id'), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    # A record belongs to exactly one executor, never reassigned on resubmission.
    submitted_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    submitted_department_id: Mapped[str | None] = mapped_column(ForeignKey('departments.id'))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    order_id: Mapped[str | None] = mapped_column(ForeignKey('orders.id', ondelete='RESTRICT'), index=True)
    order_version_id: Mapped[int | None] = mapped_column(ForeignKey('order_versions.id', ondelete='RESTRICT'))
    submitted_sha256: Mapped[str | None] = mapped_column(String(64))
    document_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    outcome_status: Mapped[str | None] = mapped_column(String(20))
    status_label: Mapped[str] = mapped_column(String(60), nullable=False, default='')
    completed_on: Mapped[date | None] = mapped_column(Date)
    result_description: Mapped[str] = mapped_column(Text, nullable=False, default='')
    indicator_actual: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    approved_by_coordinator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    measure: Mapped['Measure'] = relationship('Measure', back_populates='executions')
    order: Mapped['Order | None'] = relationship('Order')
    order_version: Mapped['OrderVersion | None'] = relationship('OrderVersion')
    submitted_by_user: Mapped['User'] = relationship('User', foreign_keys=[submitted_by_user_id])
    reviewed_by_user: Mapped['User | None'] = relationship('User', foreign_keys=[reviewed_by_user_id])
