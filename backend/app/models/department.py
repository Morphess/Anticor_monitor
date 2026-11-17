"""Організаційні підрозділи (source: pidrozdily)."""

from __future__ import annotations
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Довідник структурних підрозділів установи.
class Department(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "departments"

    # Код підрозділу з Excel, наприклад P01.
    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    # Повна офіційна/умовна назва підрозділу.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Тип підрозділу: апарат, підпорядкований, у сфері управління.
    department_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Необов’язкові пояснення; за замовчуванням порожній текст.
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Список реальних користувачів, закріплених за підрозділом.
    users: Mapped[list["User"]] = relationship("User", back_populates="department")
