"""Контракти API. Вхідні P/I перевіряємо; score/level рахує лише сервер."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MeasurementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    measured_on: date
    value: Decimal = Field(max_digits=14, decimal_places=3)
    source: str = Field(min_length=10, max_length=4000)


class MeasurementRead(MeasurementCreate):
    risk_id: str
    model_config = ConfigDict(from_attributes=True)


class AssessmentDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessed_on: date
    measurement_on: date
    probability_score: int = Field(ge=1, le=4)
    impact_score: int = Field(ge=1, le=4)
    justification: str = Field(min_length=30, max_length=10000)


class AssessmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=4000)


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    risk_id: str
    kind: Literal["baseline", "reassessment"]
    status: Literal["draft", "approved", "rejected"]
    assessed_on: date
    probability_score: int
    impact_score: int
    score: int
    level: Literal["low", "medium", "high", "critical"]
    measurement_on: date | None
    measurement_value: Decimal | None
    measurement_source: str | None
    justification: str
    created_by_user_id: int | None
    approved_by_user_id: int | None
    created_at: datetime
    decided_at: datetime | None
    decision_reason: str | None


class TrendRead(BaseModel):
    risk_id: str
    risk_title: str
    baseline_score: int | None
    current_score: int
    delta_score: int | None
    trend: Literal["not_reassessed", "decreasing", "increasing", "stable"]
    current_level: str
    latest_measurement_on: date | None
    latest_measurement_value: Decimal | None
    indicator_progress_percent: Decimal | None
    indicator_worsened_twice: bool
    history: list[AssessmentRead]
