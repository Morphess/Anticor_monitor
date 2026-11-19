"""Підтвердний матеріал виконавця, який може посилатися на номер наказу."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Evidence(Base):
    __tablename__ = "evidences"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date)
    # Номер наказу, на який посилається VYK. Це не зовнішній ключ.
    # Тип Text збережено: у БД достатньо перейменувати source_url.
    order_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Незмінне посилання на версію, зафіксовану при поданні.
    # Для старих Evidence після міграції залишиться NULL (невідома історія).
    order_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("order_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    reference_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    measure: Mapped["Measure"] = relationship("Measure", back_populates="evidences")
