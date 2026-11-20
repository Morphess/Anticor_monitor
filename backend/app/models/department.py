"""Організаційні підрозділи (source: pidrozdily)."""

from __future__ import annotations
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Довідник структурних підрозділів установи.
class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    # Повна офіційна/умовна назва підрозділу.
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Тип підрозділу: апарат, підпорядкований, у сфері управління.
    department_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Необов’язкові пояснення; за замовчуванням порожній текст.
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    parent_id: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Список реальних користувачів, закріплених за підрозділом.
    users: Mapped[list["User"]] = relationship("User", back_populates="department")
