"""Схеми нагадувань про дедлайни заходів антикорупційної програми."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DeadlineReminderItem(BaseModel):
    # D7 означає 7-денне вікно (4–7 днів); D3 — 3-денне (1–3 дні).
    id: str
    code: Literal["D7", "D3"]
    level: Literal["warning", "urgent"]
    program_id: str
    measure_id: str
    description: str
    responsible_department_id: str | None = None
    deadline_on: date
    days_left: int = Field(ge=1, le=7)
    message: str


class DeadlineRemindersRead(BaseModel):
    as_of: date
    total: int = Field(ge=0)
    warning: int = Field(ge=0)
    urgent: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    reminders: list[DeadlineReminderItem]
