"""Контракт імпорту: одна програма -> спільні розділи -> заходи.

Не імпортує розсилки чи персональні призначення: для цього є program-routing.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImportBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProgramImportData(ImportBase):
    id: str = Field(min_length=1, max_length=50, description="Унікальний ID програми")
    title: str = Field(min_length=1, description="Назва програми")
    organization_name: str = Field(min_length=1)
    start_date: date
    end_date: date
    approval_reference: str = Field(min_length=1)
    approval_status: str = Field(min_length=1)
    has_restricted_information: bool = False
    coordinator_department_id: str | None = Field(default=None, max_length=10)
    goals: str = Field(min_length=1)
    notes: str = ""
    owner_coordinator_user_id: int | None = Field(
        default=None, ge=1,
        description=("Не є полем ORM Program. Лише ADMIN може вказати KOORD-власника. "
                     "Для KOORD власником автоматично стає користувач із JWT."),
    )

    @model_validator(mode="after")
    def check_period(self) -> "ProgramImportData":
        if self.end_date < self.start_date:
            raise ValueError("end_date не може бути раніше start_date")
        return self


class MeasureImportData(ImportBase):
    id: str = Field(min_length=1, max_length=8)
    sequence_number: int = Field(ge=1)
    description: str = Field(min_length=1)
    risk_id: str | None = Field(default=None, max_length=8)
    responsible_department_id: str = Field(
        min_length=1, max_length=10,
        description="Існуючий підрозділ-відповідальний: потрібен для маршрутизації заходу",
    )
    # Сумісність зі старим JSON, де це поле завжди було null.
    # Призначення ID тут заборонено: виконавців призначає координатор через workflow.
    assigned_user_id: None = Field(default=None, description="Лише null; персональне призначення через /measures/{id}/assign")
    deadline_description: str = Field(min_length=1)
    deadline_type: Literal["date", "ongoing", "recurring"]
    deadline_on: date | None = None
    completion_indicator: str = Field(min_length=1)
    indicator_unit: str | None = Field(default=None, max_length=20)
    indicator_target: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3, allow_inf_nan=False
    )
    required_evidence: str = Field(min_length=1)
    resources: str = Field(min_length=1)
    collaborator_department_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_deadline(self) -> "MeasureImportData":
        if self.deadline_type == "date" and self.deadline_on is None:
            raise ValueError("для deadline_type='date' потрібне deadline_on")
        if self.deadline_type != "date" and self.deadline_on is not None:
            raise ValueError("для ongoing/recurring deadline_on має бути null")
        if len(self.collaborator_department_ids) != len(set(self.collaborator_department_ids)):
            raise ValueError("співвиконавці одного заходу не повинні дублюватися")
        if any(not x or len(x) > 10 or x != x.strip() for x in self.collaborator_department_ids):
            raise ValueError("некоректний ID підрозділу-співвиконавця")
        return self


class SectionImportData(ImportBase):
    id: str = Field(min_length=1, max_length=4)
    number: int = Field(ge=1)
    title: str = Field(min_length=1)
    measures: list[MeasureImportData] = Field(default_factory=list)


class ProgramImportPayload(ImportBase):
    program: ProgramImportData
    sections: list[SectionImportData] = Field(min_length=1)

    @model_validator(mode="after")
    def check_uniqueness(self) -> "ProgramImportPayload":
        section_ids: set[str] = set()
        section_numbers: set[int] = set()
        measure_ids: set[str] = set()
        for section in self.sections:
            if section.id in section_ids:
                raise ValueError(f"розділ {section.id} повторюється")
            if section.number in section_numbers:
                raise ValueError(f"номер розділу {section.number} повторюється")
            section_ids.add(section.id)
            section_numbers.add(section.number)
            seqs: set[int] = set()
            for measure in section.measures:
                if measure.id in measure_ids:
                    raise ValueError(f"ID заходу {measure.id} повторюється")
                if measure.sequence_number in seqs:
                    raise ValueError(
                        f"у розділі {section.id} номер заходу {measure.sequence_number} повторюється"
                    )
                measure_ids.add(measure.id)
                seqs.add(measure.sequence_number)
        if not measure_ids:
            raise ValueError("JSON повинен містити щонайменше один захід")
        return self


class ProgramImportResult(BaseModel):
    program_id: str
    created_by_user_id: int | None
    coordinator_department_id: str | None
    sections_created: int
    sections_reused: int
    measures_created: int
    collaborators_created: int
    dispatches_created: int = 0
    assignments_created: int = 0
