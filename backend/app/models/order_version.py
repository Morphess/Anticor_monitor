"""Незмінна версія вмісту наказу; SHA-256 рахується лише на сервері."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Integer, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class OrderVersion(Base):
    __tablename__ = "order_versions"
    __table_args__ = (
        UniqueConstraint("order_id", "version", name="uq_order_version_number"),
        CheckConstraint("version >= 1", name="ck_order_version_positive"),
        CheckConstraint("size_bytes > 0", name="ck_order_version_nonempty"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Зберігаємо лише серверний випадковий ключ; не абсолютний шлях/URL користувача.
    storage_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Поки реєстр редагується локально, автентифікованого оператора немає.
    uploaded_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
