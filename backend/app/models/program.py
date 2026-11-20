from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


# Паспорт антикорупційної програми та її загальні параметри.
class Program(Base):
    __tablename__ = "programs"

    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="ck_program_dates",
        ),
    )

    # Унікальний текстовий код програми.
    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    # Назва антикорупційної програми.
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Організація, яка затвердила програму.
    organization_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Період дії програми.
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # Реквізити документа про затвердження.
    approval_reference: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Статус погодження програми.
    approval_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Ознака інформації з обмеженим доступом.
    has_restricted_information: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Підрозділ, який координує програму.
    coordinator_department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"),
        nullable=True,
    )

    # Цілі антикорупційної програми.
    goals: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Додаткові примітки.
    notes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    # Користувач, який створив програму (MAIN_KOORD).
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Зв'язок із підрозділом-координатором.
    coordinator_department: Mapped["Department | None"] = relationship(
        "Department",
    )

    # Користувачі, прив'язані до програми через users.program_id.
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="program",
        foreign_keys="User.program_id",
    )

    # Заходи антикорупційної програми.
    measures: Mapped[list["Measure"]] = relationship(
        "Measure",
        back_populates="program",
    )
