"""Моделі доступу до програм і призначень на заходи.

НЕ дублюють Program / Measure / User; використовують їхні чинні PK.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Integer, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProgramDepartment(Base):
    __tablename__ = "program_departments"
    __table_args__ = (Index("ix_program_departments_department_id", "department_id"),)

    program_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True
    )
    sent_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MeasureAssignment(Base):
    __tablename__ = "measure_assignments"
    __table_args__ = (
        Index("ix_measure_assignments_user_id", "user_id"),
        Index("ix_measure_assignments_department_id", "department_id"),
    )

    measure_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("measures.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
