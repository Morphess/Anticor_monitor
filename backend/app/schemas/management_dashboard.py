"""Read-only data contracts for the KER (department head) dashboard."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DepartmentKPI(BaseModel):
    department_id: str | None
    department_name: str
    total: int
    approved_completed: int
    overdue: int
    awaiting_approval: int


class ManagementSummary(BaseModel):
    department_id: str
    department_name: str
    scope_department_ids: list[str]
    program_ids: list[str]
    period: str
    as_of: date
    total: int
    completed: int  # Статус completed, навіть якщо не погоджено.
    approved_completed: int
    partial: int
    in_progress: int
    not_completed: int
    not_started: int
    awaiting_approval: int
    overdue: int
    due_soon: int
    approved_completion_percent: float
    high_risks: int
    critical_risks: int
    departments: list[DepartmentKPI] = Field(default_factory=list)


class ManagementDeadline(BaseModel):
    program_id: str
    measure_id: str
    description: str
    responsible_department_id: str | None
    deadline_on: date
    days_left: int
    status: str
    approved: bool
    category: Literal["overdue", "upcoming"]


class ManagementRisk(BaseModel):
    program_id: str
    risk_id: str
    title: str
    level: Literal["low", "medium", "high", "critical"]
    owner_department_id: str | None
    indicator_name: str
    indicator_direction: str
    baseline: Decimal
    target: Decimal
    actual: Decimal | None
    measured_on: date | None
    trend: Literal["improved", "worsened", "unchanged", "no_data"]
    target_reached: bool | None
    has_measures_in_program: bool


class ManagementRecommendation(BaseModel):
    key: str
    code: str
    program_id: str
    object_type: str
    object_id: str
    priority: Literal["critical", "high", "medium", "low"]
    title: str
    reason: str
    suggestion: str
    source: Literal["risk_flag", "operational"]
    as_of: date


class ManagementRecommendationsResponse(BaseModel):
    department_id: str
    period: str
    as_of: date
    total: int
    recommendations: list[ManagementRecommendation] = Field(default_factory=list)
