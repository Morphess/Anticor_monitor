from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


# Захід антикорупційної програми:
# план, строки, відповідальні та очікуваний результат.
class Measure(Base):
    __tablename__ = "measures"

    # Обмеження цілісності бази даних.
    __table_args__ = (
        # Номер заходу унікальний у межах програми та розділу.
        UniqueConstraint(
            "program_id",
            "section_id",
            "sequence_number",
            name="uq_measure_number_in_program_section",
        ),
        # Допустимі типи строків виконання.
        CheckConstraint(
            "deadline_type IN ('date', 'ongoing', 'recurring')",
            name="ck_measure_deadline_type",
        ),
        # Якщо строк визначений датою,
        # поле deadline_on обов'язкове.
        CheckConstraint(
            "deadline_type <> 'date' OR deadline_on IS NOT NULL",
            name="ck_measure_date_required",
        ),
    )

    # ==========================================
    # ОСНОВНІ ІДЕНТИФІКАТОРИ
    # ==========================================

    # Унікальний текстовий код заходу, наприклад Z-01.
    id: Mapped[str] = mapped_column(String(8), primary_key=True)

    # Програма, до якої належить захід.
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), nullable=False)

    # Розділ R1, R2 або R3.
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"), nullable=False)

    # Порядковий номер заходу всередині розділу програми.
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # ==========================================
    # ІНФОРМАЦІЯ ПРО ЗАХІД
    # ==========================================

    # Повний опис заходу.
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Корупційний ризик, пов'язаний із заходом.
    # Для розділів R1 та R3 може бути NULL.
    risk_id: Mapped[str | None] = mapped_column(ForeignKey("risks.id"), nullable=True)

    # Головний відповідальний підрозділ.
    responsible_department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )

    # Користувач, якому призначено захід.
    assigned_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # ==========================================
    # СТРОКИ ВИКОНАННЯ
    # ==========================================

    # Первісний текст строку.
    deadline_description: Mapped[str] = mapped_column(Text, nullable=False)

    # date, ongoing або recurring.
    deadline_type: Mapped[str] = mapped_column(String(12), nullable=False)

    # Конкретна дата завершення, якщо застосовується.
    deadline_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ==========================================
    # ПОКАЗНИКИ ТА РЕСУРСИ
    # ==========================================

    # Очікуваний результат заходу.
    completion_indicator: Mapped[str] = mapped_column(Text, nullable=False)

    # Одиниця вимірювання (% або шт.).
    indicator_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Планове числове значення.
    indicator_target: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )

    # Необхідні підтвердні документи.
    required_evidence: Mapped[str] = mapped_column(Text, nullable=False)

    # Необхідні ресурси.
    resources: Mapped[str] = mapped_column(Text, nullable=False)

    # ==========================================
    # ORM-ЗВ'ЯЗКИ
    # ==========================================

    # Програма заходу.
    program: Mapped["Program"] = relationship("Program", back_populates="measures")

    # Розділ заходу.
    section: Mapped["Section"] = relationship("Section", back_populates="measures")

    # Корупційний ризик.
    risk: Mapped["Risk | None"] = relationship("Risk", back_populates="measures")

    # Відповідальний підрозділ.
    responsible_department: Mapped["Department | None"] = relationship("Department")

    # Призначений користувач.
    assigned_user: Mapped["User | None"] = relationship("User")

    # Співвиконавці заходу.
    collaborators: Mapped[list["MeasureCollaborator"]] = relationship(
        "MeasureCollaborator", back_populates="measure", cascade="all, delete-orphan"
    )

    # Звіти про виконання.
    executions: Mapped[list["Execution"]] = relationship(
        "Execution", back_populates="measure"
    )

    # Рішення про перенесення строків.
    deadline_changes: Mapped[list["DeadlineChange"]] = relationship(
        "DeadlineChange", back_populates="measure"
    )


# ==========================================
# СПІВВИКОНАВЦІ ЗАХОДУ
# ==========================================


# Зв'язок багато-до-багатьох:
# один захід може мати декілька підрозділів-співвиконавців.
class MeasureCollaborator(Base):
    __tablename__ = "measure_collaborators"

    # Код заходу.
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), primary_key=True)

    # Код підрозділу-співвиконавця.
    department_id: Mapped[str] = mapped_column(
        ForeignKey("departments.id"), primary_key=True
    )

    # ORM-зв'язок із заходом.
    measure: Mapped["Measure"] = relationship("Measure", back_populates="collaborators")

    # ORM-зв'язок із підрозділом.
    department: Mapped["Department"] = relationship("Department")
