"""Модель підтвердного документа заходу."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Evidence(Base):
    __tablename__ = "evidences"

    id: Mapped[str] = mapped_column(
        String(12),
        primary_key=True,
    )

    measure_id: Mapped[str] = mapped_column(
        ForeignKey("measures.id"),
        nullable=False,
    )

    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    document_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Номер наказу, який зазначає VYK.
    # Замість старого поля source_url.
    order_number: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )

    reference_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    measure: Mapped["Measure"] = relationship(
        "Measure",
        back_populates="evidences",
    )
