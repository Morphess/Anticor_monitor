"""Накази: приклад доменної сутності, її немає в тестовому CSV."""

from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Наказ, пов'язаний із конкретним заходом програми
class Order(Base):

    # Таблиця наказів у PostgreSQL
    __tablename__ = "orders"

    # Унікальний ідентифікатор наказу в системі
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Реєстраційний номер наказу
    number: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    # Назва або тема наказу
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Дата видання наказу
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Шлях або посилання на електронний документ
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ID заходу, до якого належить наказ
    # Наприклад: "Z-05"
    # ForeignKey посилається на таблицю measures
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), nullable=False)

    # Дата та час створення запису про наказ у БД
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Отримання самого заходу через ORM
    measure: Mapped[Measure] = relationship("Measure", back_populates="orders")
