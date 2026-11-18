"""Вхідні та вихідні схеми передачі програми / призначення заходів."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DispatchDepartmentsIn(BaseModel):
    department_ids: list[str] = Field(min_length=1)


class DepartmentScopeRead(BaseModel):
    id: str
    name: str
    parent_id: str | None


class CoordinatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    role_id: str
    department_id: str | None


class DepartmentDispatchRead(BaseModel):
    department_id: str
    coordinators: list[CoordinatorRead]
    already_sent: bool = False


class DispatchDepartmentsOut(BaseModel):
    program_id: str
    departments: list[DepartmentDispatchRead]


class ProgramAccessRead(BaseModel):
    id: str
    title: str
    access_type: str   # admin | owner | department_coordinator | executor


class SectionBriefRead(BaseModel):
    id: str
    number: int
    title: str


class MeasureBriefRead(BaseModel):
    id: str
    program_id: str
    section_id: str
    description: str
    responsible_department_id: str | None


class AssignMeasureIn(BaseModel):
    department_id: str = Field(min_length=1)
    user_id: int = Field(gt=0)


class MeasureAssignmentRead(BaseModel):
    measure_id: str
    user_id: int
    department_id: str
    assigned_by_user_id: int | None
    assigned_at: datetime


class AssignmentResult(BaseModel):
    assignment: MeasureAssignmentRead
    already_assigned: bool
