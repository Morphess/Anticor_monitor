from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


class Evidence(Base):
    __tablename__ = "evidences"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # E-001
    measure_id: Mapped[str] = mapped_column(ForeignKey("measures.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # document names may repeat
    document_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(
        Text
    )  # URL is not a ForeignKey to orders
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )

    reference_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # synthetic metadata hash, not file bytes

    measure: Mapped["Measure"] = relationship("Measure", back_populates="evidences")
