"""Підтвердні матеріали та поточний результат перевірки номера наказу."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


from app.schemas.orders import OrderCheckStatus


class EvidenceBase(BaseModel):
    measure_id: str = Field(min_length=1, max_length=8)
    document_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1)
    document_date: date | None = None
    reference_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    # Замість колишнього source_url: номер наказу або None.
    order_number: str | None = Field(default=None, max_length=150)

    @field_validator("order_number", mode="before")
    @classmethod
    def strip_order_number(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value


class EvidenceCreate(EvidenceBase):
    id: str = Field(min_length=1, max_length=12)


class EvidenceUpdate(BaseModel):
    measure_id: str | None = Field(default=None, min_length=1, max_length=8)
    document_type: str | None = Field(default=None, min_length=1, max_length=50)
    title: str | None = Field(default=None, min_length=1)
    document_date: date | None = None
    reference_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    order_number: str | None = Field(default=None, max_length=150)

    @field_validator("order_number", mode="before")
    @classmethod
    def strip_order_number(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value


class EvidenceRead(EvidenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    uploaded_at: datetime
    order_version_id: int | None = None
    order_version_number: int | None = None
    order_version_is_current: bool | None = None
    # Це обчислюється при читанні з реєстру, а не зберігається в evidences.
    order_check_status: OrderCheckStatus = "not_provided"
