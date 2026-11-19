"""Аудит відхилених номерів наказів, які VYK вводив у Evidence."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class InvalidOrderReference(Base):
    __tablename__ = "invalid_order_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    measure_id: Mapped[str] = mapped_column(
        ForeignKey("measures.id"), nullable=False, index=True,
    )
    # Зберігаємо ID як історичні метадані, не вимагаємо FK до users.
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    order_number: Mapped[str] = mapped_column(String(150), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)  # create / update
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
