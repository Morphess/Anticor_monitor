"""Pydantic-схеми реєстру наказів."""

from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


OrderCheckStatus = Literal[
    "found",
    "not_found",
    "not_provided",
]


class OrderBase(BaseModel):
    number: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1)
    issued_on: date | None = None
    document_url: str | None = None

    @field_validator("number", "title")
    @classmethod
    def trim_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Поле не може бути порожнім")
        return value


class OrderCreate(OrderBase):
    id: str = Field(min_length=1, max_length=50)

    @field_validator("id")
    @classmethod
    def trim_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ID не може бути порожнім")
        return value


class OrderUpdate(BaseModel):
    number: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    title: str | None = Field(default=None, min_length=1)
    issued_on: date | None = None
    document_url: str | None = None

    @field_validator("number", "title")
    @classmethod
    def trim_nonnull(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Поле не може бути порожнім")
        return value


class OrderRead(OrderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class OrderCheckRead(BaseModel):
    number: str | None
    status: OrderCheckStatus
