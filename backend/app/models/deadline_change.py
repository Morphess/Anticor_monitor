"""Внутрішнє погодження перенесення строку, не змінює затверджений план."""

from __future__ import annotations
from datetime import date
from sqlalchemy import Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Окреме рішення про перенесення строку заходу; первинний строк заходу не перезаписуємо.
class DeadlineChange(Base):
    __tablename__ = "deadline_changes"

    # Внутрішній автоматично створюваний номер рішення про перенесення.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Захід, строк якого пропонують перенести (FK → measures.id).
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), nullable=False)
    # Коли ухвалили рішення про перенесення.
    decision_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Строк, який діяв до рішення.
    previous_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    # Новий внутрішньо погоджений строк.
    new_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    # Обґрунтування причини перенесення.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Хто ухвалив рішення про перенесення (FK → users.id);
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # ORM-посилання на сам захід.
    measure: Mapped["Measure"] = relationship(
        "Measure", back_populates="deadline_changes"
    )
    user: Mapped["User | None"] = relationship("User")
