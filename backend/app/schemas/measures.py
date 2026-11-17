from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Основні поля заходу
class MeasureBase(BaseModel):

    program_id: str = Field(min_length=1, max_length=50)
    section_id: str = Field(min_length=1, max_length=4)

    sequence_number: int = Field(ge=1)

    description: str = Field(min_length=1)

    risk_id: str | None = Field(default=None, max_length=8)

    responsible_department_id: str | None = Field(default=None, max_length=8)

    assigned_user_id: int | None = Field(default=None, ge=1)

    deadline_description: str = Field(min_length=1)

    deadline_type: Literal["date", "ongoing", "recurring"]

    deadline_on: date | None = None

    completion_indicator: str = Field(min_length=1)

    indicator_unit: str | None = Field(default=None, max_length=20)

    indicator_target: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3
    )

    required_evidence: str = Field(min_length=1)
    resources: str = Field(min_length=1)

    # Якщо тип строку date, дата обов'язкова
    @model_validator(mode="after")
    def check_deadline(self):

        if self.deadline_type == "date" and self.deadline_on is None:
            raise ValueError("Для deadline_type='date' вкажи deadline_on")

        return self


# Створення заходу
class MeasureCreate(MeasureBase):

    id: str = Field(min_length=1, max_length=8)


# Часткове редагування заходу
class MeasureUpdate(BaseModel):

    program_id: str | None = Field(default=None, min_length=1, max_length=50)

    section_id: str | None = Field(default=None, min_length=1, max_length=4)

    sequence_number: int | None = Field(default=None, ge=1)

    description: str | None = Field(default=None, min_length=1)

    risk_id: str | None = Field(default=None, max_length=8)

    responsible_department_id: str | None = Field(default=None, max_length=8)

    assigned_user_id: int | None = Field(default=None, ge=1)

    deadline_description: str | None = Field(default=None, min_length=1)

    deadline_type: Literal["date", "ongoing", "recurring"] | None = None

    deadline_on: date | None = None

    completion_indicator: str | None = Field(default=None, min_length=1)

    indicator_unit: str | None = Field(default=None, max_length=20)

    indicator_target: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3
    )

    required_evidence: str | None = Field(default=None, min_length=1)

    resources: str | None = Field(default=None, min_length=1)


# Дані, які повертає API
class MeasureRead(MeasureBase):

    model_config = ConfigDict(from_attributes=True)

    id: str
