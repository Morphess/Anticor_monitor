from __future__ import annotations
from sqlalchemy import Integer, String, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Розділ конкретної антикорупційної програми.
class Section(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "sections"
    # Правила цілісності БД: унікальність і перевірки значень.
    # У межах однієї програми не може бути двох розділів із тим самим номером.
    __table_args__ = (
        UniqueConstraint("number", name="uq_sections_number"),
        CheckConstraint("number > 0", name="ck_sections_number_positive"),
    )

    # Код розділу: R1, R2 або R3 у тестовому наборі.
    id: Mapped[str] = mapped_column(String(4), primary_key=True)  # R1, R2, R3 (demo ID)

    # Порядковий номер розділу для відображення.
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Повна назва розділу.
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Усі заходи цього розділу.
    measures: Mapped[list["Measure"]] = relationship(
        "Measure", back_populates="section"
    )
