"""Schemas for the order-based approval workflow."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

ExecutionStatus = Literal["pending", "approved", "rejected"]


class ExecutionSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    measure_id: str = Field(min_length=1, max_length=8)
    period: str = Field(pattern=r"^\d{4}-H[12]$")
    order_number: str = Field(min_length=1, max_length=150)


class ExecutionReject(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=2000)


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
    # Client fetches with JWT; a plain <a href> would not carry Bearer token.
    document_api_path: str | None = None
