"""Відповідь автоматичного звіту за півріччя.

Три основні поля рядка відповідають структурі звіту Порталу доброчесності.
Додаткові поля використовуються для внутрішнього контролю і перевірки.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ReportMeasureRow(BaseModel):
    measure_id: str
    sequence_number: int | None = None
    measure_description: str
    responsible_department_id: str | None = None
    responsible_department: str | None = None
    risk_id: str | None = None
    factual_date: date | None = None
    execution_status: str
    result_description: str
    indicator_actual: Decimal | None = None
    indicator_target: Decimal | None = None
    approved_by_coordinator: bool = False
    evidence_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ReportSectionBlock(BaseModel):
    section_id: str
    number: int
    title: str
    measures: list[ReportMeasureRow] = Field(default_factory=list)


class ReportSummary(BaseModel):
    total: int = 0
    completed: int = 0
    partial: int = 0
    not_completed: int = 0
    not_due: int = 0
    unapproved: int = 0
    missing_explanations: int = 0


class PortalHalfYearReport(BaseModel):
    program_id: str
    program_title: str
    period: str
    period_start: date
    period_end: date
    as_of: date
    is_preliminary: bool
    generated_at: datetime
    scope: Literal["program", "department"]
    department_id: str | None = None
    sections: list[ReportSectionBlock]
    summary: ReportSummary
