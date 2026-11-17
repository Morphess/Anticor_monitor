"""Збережені експорти/версії звітів; CSV zvit_portal є контрольним результатом, не seed таблиці."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Запис про сформовану/подану версію звіту, а не сам вміст звіту.
class Report(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "reports"
    # Правила цілісності БД: унікальність і перевірки значень.
    __table_args__ = (
        # Одна версія звіту для певної програми й періоду може існувати лише раз.
        UniqueConstraint("program_id", "period", "version", name="uq_report_version"),
        # Номер версії звіту починається з 1.
        CheckConstraint("version >= 1", name="ck_report_version"),
        # Три можливі стани звіту: чернетка, сформований, поданий.
        CheckConstraint(
            "status IN ('draft', 'generated', 'submitted')", name="ck_report_status"
        ),
    )

    # Автоматичний номер сформованого звіту.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Для якої програми підготовлений звіт.
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), nullable=False)
    # За який період, наприклад 2026-H1.
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # 2026-H1
    # Номер версії звіту, починаючи з 1.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Чернетка, сформований чи поданий: draft/generated/submitted.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # Коли запис про звіт створено (час сервера БД з часовою зоною).
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Обліковий запис того, хто сформував звіт; може бути NULL.
    generated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Шлях до збереженого файлу звіту, якщо його експортували.
    export_file_path: Mapped[str | None] = mapped_column(Text)

    # ORM-доступ до програми звіту.
    program: Mapped["Program"] = relationship("Program")
    # ORM-доступ до користувача, який створив звіт.
    generated_by_user: Mapped["User | None"] = relationship("User")
