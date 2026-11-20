"""Відповідь автоматичного звіту за півріччя.

Три основні поля рядка відповідають структурі звіту Порталу доброчесності.
Додаткові поля використовуються для внутрішнього контролю і перевірки.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReportRisk(BaseModel):
    """Шапка групи заходів у розділі «Заходи з усунення корупційних ризиків»."""
    risk_id: str
    sphere: str | None = None  # «Сфера ризику» — процес, у якому виникає ризик
    title: str | None = None   # «Назва ризику»
    description: str | None = None  # «Опис ризику»
    level: str | None = None


class ReportMeasureRow(BaseModel):
    measure_id: str
    sequence_number: int | None = None
    measure_description: str
    # Відповідальний підрозділ = підрозділи призначених виконавців
    # (а не підрозділ того, хто створив захід).
    responsible_department_id: str | None = None
    responsible_department: str | None = None
    planned_deadline: str | None = None  # «Запланований строк виконання заходу»
    completion_indicator: str | None = None  # «Індикатор виконання»
    indicator_unit: str | None = None
    participants_count: int | None = None  # розділ 3: «Кількість осіб, які взяли участь у навчанні»
    risk_id: str | None = None
    risk: ReportRisk | None = None
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
    missing_results: int = 0


class PortalHalfYearReport(BaseModel):
    program_id: str
    program_title: str
    organization_name: str | None = None  # «Орган: …» у шапці звіту НАЗК
    period_label: str | None = None  # «Звіт за перше півріччя 2026 року»
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


class ReportMeasureOverride(BaseModel):
    """Coordinator-authored narrative in a newly generated report version."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    measure_id: str = Field(min_length=1, max_length=8)
    execution_status: Literal["Виконано", "Частково виконано", "Не виконано"] | None = None
    result_description: str | None = Field(default=None, max_length=4000)
    factual_date: date | None = None
    indicator_actual: Decimal | None = None
    participants_count: int | None = Field(default=None, ge=0, le=1000000)

    @field_validator("result_description")
    @classmethod
    def no_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any((ord(c) < 32 and c not in "\n\t") for c in value):
            raise ValueError("Опис має містити лише допустимі символи")
        return value


class ReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: list[ReportMeasureOverride] = Field(default_factory=list, max_length=2000)
