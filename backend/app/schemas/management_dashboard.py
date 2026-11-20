"""Read-only data contracts for the KER (department head) dashboard."""
from __future__ import annotations

from datetime import date, datetime
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
    # agency — керівник відомства (підрозділ без батька): усі створені програми;
    # department — керівник підрозділу: лише програми, координовані на його підрозділ.
    scope: Literal["agency", "department"] = "department"


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


class ManagementUnit(BaseModel):
    department_id: str
    department_name: str


class ManagementDispatch(ManagementUnit):
    sent_at: datetime | None = None


class ManagementProgram(BaseModel):
    id: str
    title: str
    start_date: date | None
    end_date: date | None
    coordinator_department_id: str | None
    coordinator_department_name: str | None
    # Кому координовано програму (program_departments) у межах видимості керівника.
    dispatched_to: list[ManagementDispatch] = Field(default_factory=list)
    measures_total: int


class ManagementMeasure(BaseModel):
    program_id: str
    program_title: str
    # Whether execution and status data are within this KER's own department tree.
    # Out-of-scope measures remain visible as programme passport entries only.
    in_scope: bool = True
    section_id: str | None
    section_number: int | None
    section_title: str | None
    measure_id: str
    sequence_number: int | None
    description: str
    responsible_department_id: str | None
    responsible_department_name: str | None
    # Відділи гілки керівника підрозділу, яким доручено захід; без користувачів.
    # Керівнику відомства не віддається (лише підрозділ-адресат програми).
    assigned_units: list[ManagementUnit] = Field(default_factory=list)
    deadline_type: str | None
    deadline_on: date | None
    deadline_description: str | None
    status: str
    approved: bool
    submitted_at: datetime | None
    completed_on: date | None
    indicator_target: Decimal | None
    indicator_actual: Decimal | None


class ManagementMeasureAssignmentProgress(BaseModel):
    measure_id: str
    assigned: int
    approved: int
    pending: int
    rejected: int
    not_submitted: int


class ManagementDepartmentProgress(BaseModel):
    department_id: str
    department_name: str
    is_own_department: bool
    measures_total: int
    measures_approved: int
    assigned: int
    approved: int
    pending: int
    rejected: int
    not_submitted: int
    measures: list[ManagementMeasureAssignmentProgress] = Field(default_factory=list)


class ManagementDepartmentProgressResponse(BaseModel):
    department_id: str
    period: str
    program_id: str | None = None
    measures_total: int
    unassigned_measures: int
    departments: list[ManagementDepartmentProgress] = Field(default_factory=list)
