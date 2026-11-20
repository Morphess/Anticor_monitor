"""Контракти відповіді Dashboard. Дані — поточний зріз, не збережена версія звіту."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    program_id: str
    program_title: str
    period: str
    as_of: date
    scope: Literal["program", "department", "executor"]
    total: int = 0
    completed: int = 0
    approved_completed: int = 0
    partial: int = 0
    in_progress: int = 0
    not_completed: int = 0
    not_started: int = 0
    unapproved: int = 0
    completion_percent: float = 0.0
    approved_completion_percent: float = 0.0
    overdue: int = 0
    due_soon: int = 0
    upcoming_days: int = 14


class DepartmentProgress(BaseModel):
    department_id: str | None = None
    department_name: str
    total: int
    completed: int
    approved_completed: int
    overdue: int
    completion_percent: float


class DepartmentDashboard(BaseModel):
    program_id: str
    period: str
    as_of: date
    attribution: str = "responsible_department_only"
    departments: list[DepartmentProgress] = Field(default_factory=list)


class RiskIndicator(BaseModel):
    risk_id: str
    title: str
    level: Literal["low", "medium", "high", "critical"]
    owner_department_id: str | None = None
    indicator_name: str
    indicator_unit: str
    indicator_direction: Literal["increase", "decrease"]
    baseline: Decimal
    target: Decimal
    current: Decimal | None = None
    measured_on: date | None = None
    progress_percent: float | None = None
    trend: Literal["improved", "worsened", "unchanged", "no_data"]
    target_reached: bool | None = None
    has_measures_in_program: bool


class RiskDashboard(BaseModel):
    program_id: str
    as_of: date
    total: int
    high: int
    critical: int
    unmeasured: int
    without_measures: int
    risks: list[RiskIndicator] = Field(default_factory=list)


class DeadlineItem(BaseModel):
    measure_id: str
    description: str
    deadline_on: date
    days_until: int  # від'ємне значення = прострочено
    responsible_department_id: str | None = None
    execution_status: str
    approved_by_coordinator: bool


class DeadlineDashboard(BaseModel):
    program_id: str
    period: str
    as_of: date
    horizon_days: int
    overdue_total: int
    upcoming_total: int
    overdue: list[DeadlineItem] = Field(default_factory=list)
    upcoming: list[DeadlineItem] = Field(default_factory=list)


class MyDashboard(BaseModel):
    summary: DashboardSummary
    deadlines: DeadlineDashboard
    risks: RiskDashboard
