from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


# Запит керівника до аналітика: що з'ясувати, щодо якої програми й до якого строку.
class AnalyticsRequest(Base):
    __tablename__ = "analytics_requests"
    __table_args__ = (
        CheckConstraint("status IN ('new', 'in_progress', 'answered')", name="ck_analytics_request_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # NULL — усі програми
    program_id: Mapped[str | None] = mapped_column(ForeignKey("programs.id"))
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    # new — надіслано; in_progress — аналітик узяв у роботу; answered — звіт надіслано
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="new")

    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    analyst_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    program: Mapped["Program | None"] = relationship("Program")
    requested_by: Mapped["User"] = relationship("User", foreign_keys=[requested_by_user_id])
    analyst: Mapped["User | None"] = relationship("User", foreign_keys=[analyst_user_id])
    report: Mapped["AnalyticsReport | None"] = relationship("AnalyticsReport", back_populates="request", uselist=False)


# Аналітичний звіт: висновки аналітика + незмінний зріз даних на момент надсилання.
class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Звіт на запит керівника або з власної ініціативи аналітика (NULL)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("analytics_requests.id"), unique=True)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("programs.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    findings: Mapped[str] = mapped_column(Text, nullable=False)
    proposals: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Показники, розподіл за розділами й підрозділами, прострочені заходи — як було на момент звіту
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)

    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    # Коли керівник уперше відкрив звіт
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    request: Mapped["AnalyticsRequest | None"] = relationship("AnalyticsRequest", back_populates="report")
    program: Mapped["Program | None"] = relationship("Program")
    author: Mapped["User"] = relationship("User")
