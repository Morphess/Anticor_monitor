"""Completed AI reports, bound to the exact submitted document and analysis input."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class ExecutionAnalysis(Base):
    __tablename__ = "execution_analyses"
    __table_args__ = (Index("ix_execution_analyses_lookup", "execution_id", "order_version_id",
                           "submitted_sha256", "input_sha256", "analysis_id"),)

    analysis_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(50), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    order_version_id: Mapped[int] = mapped_column(ForeignKey("order_versions.id", ondelete="RESTRICT"), nullable=False)
    submitted_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    analysis: Mapped[str] = mapped_column(Text, nullable=False)
    text_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    output_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                server_default=func.clock_timestamp())
