"""Schemas for the order-based approval workflow."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

ExecutionStatus = Literal["pending", "approved", "rejected"]
# Стан, який виконавець заявляє у звіті (для Порталу доброчесності НАЗК):
# «Виконано» або «Частково виконано». «Не виконано» і «Строк не настав»
# система визначає сама, коли погодженого виконання немає.
ExecutionOutcome = Literal["completed", "partial"]


class ExecutionSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    measure_id: str = Field(min_length=1, max_length=8)
    period: str = Field(pattern=r"^\d{4}-H[12]$")
    order_number: str = Field(min_length=1, max_length=150)
    # Опис результату виконання — обов'язкове поле звіту НАЗК. Має описувати
    # вимірюваний результат, а не повторювати зміст заходу.
    result_description: str = Field(min_length=10, max_length=4000)
    outcome_status: ExecutionOutcome = "completed"
    # Фактична дата виконання; якщо не передано — дата подання.
    completed_on: date | None = None
    # Фактичне значення індикатора виконання. Для навчальних заходів
    # (розділ 3 звіту) — кількість осіб, які взяли участь.
    indicator_actual: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)


class ExecutionChangeOrder(BaseModel):
    """Only executor may replace the order for an already pending submission."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    order_number: str = Field(min_length=1, max_length=150)


class ExecutionReviewGuard(BaseModel):
    """Prevent approving a different order than the coordinator reviewed."""
    model_config = ConfigDict(extra="forbid")
    expected_order_version_id: int | None = None
    expected_submitted_at: datetime | None = None


class ExecutionReject(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=2000)
    expected_order_version_id: int | None = None
    expected_submitted_at: datetime | None = None


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    measure_id: str
    period: str
    status: ExecutionStatus
    order_id: str | None
    order_number: str | None = None
    order_version_id: int | None
    submitted_sha256: str | None
    document_changed: bool
    submitted_by_user_id: int | None
    submitted_department_id: str | None
    submitted_at: datetime | None
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    # Дані для звіту НАЗК, заявлені виконавцем.
    outcome_status: str | None = None
    completed_on: date | None = None
    result_description: str | None = None
    indicator_actual: Decimal | None = None
    # Client fetches with JWT; a plain <a href> would not carry Bearer token.
    document_api_path: str | None = None
