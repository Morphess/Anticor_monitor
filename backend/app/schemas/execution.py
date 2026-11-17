"""Pydantic-схеми звітності про виконання заходів."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExecutionStatus = Literal[
    "completed",
    "partial",
    "not_completed",
    "in_progress",
    "not_started",
]


class ExecutionBase(BaseModel):
    """Дані, які користувач може заповнити у звіті."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: ExecutionStatus
    status_label: str = Field(min_length=1, max_length=60)
    completed_on: date | None = None
    result_description: str = ""
    indicator_actual: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3
    )


class ExecutionCreate(ExecutionBase):
    """Новий звіт: один запис на захід і звітний період."""

    measure_id: str = Field(min_length=1)
    period: str = Field(min_length=1, max_length=20, examples=["2026-H1"])


class ExecutionUpdate(BaseModel):
    """Часткове оновлення без зміни складеного первинного ключа."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: ExecutionStatus | None = None
    status_label: str | None = Field(default=None, min_length=1, max_length=60)
    completed_on: date | None = None
    result_description: str | None = None
    indicator_actual: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3
    )

    @model_validator(mode="after")
    def prohibit_null_in_required_fields(self) -> Self:
        """PATCH не може встановлювати NULL для NOT NULL-полів."""
        for field_name in ("status", "status_label", "result_description"):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"Поле '{field_name}' не може бути null")
        return self


class ExecutionRead(ExecutionCreate):
    """Схема відповіді; службові поля доступні тільки на читання."""

    model_config = ConfigDict(from_attributes=True)

    submitted_by_user_id: int | None
    submitted_at: datetime | None
    approved_by_coordinator: bool


class ExecutionApprovalUpdate(BaseModel):
    """Погодження звіту координатором."""

    approved_by_coordinator: bool
