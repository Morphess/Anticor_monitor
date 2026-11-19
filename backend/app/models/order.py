"""Модель незалежного реєстру наказів."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (UniqueConstraint("number", name="uq_orders_number"),)

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    number: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    issued_on: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    document_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
