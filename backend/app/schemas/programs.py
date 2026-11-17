from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Спільні поля антикорупційної програми.
class ProgramBase(BaseModel):
    title: str = Field(min_length=1)
    organization_name: str = Field(min_length=1)

    start_date: date
    end_date: date

    approval_reference: str = Field(min_length=1)
    approval_status: str = Field(min_length=1)

    has_restricted_information: bool = False

    # Підрозділ-координатор необов'язковий.
    coordinator_department_id: str | None = None

    goals: str = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError(
                "Дата завершення програми не може " "бути раніше дати початку"
            )
        return self


# Дані для створення нової програми.
class ProgramCreate(ProgramBase):
    id: str = Field(
        min_length=1,
        max_length=50,
        examples=["AKP-UV-2026-2027"],
    )


# Дані для часткового редагування програми.
class ProgramUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
    )
    organization_name: str | None = Field(
        default=None,
        min_length=1,
    )

    start_date: date | None = None
    end_date: date | None = None

    approval_reference: str | None = Field(
        default=None,
        min_length=1,
    )
    approval_status: str | None = Field(
        default=None,
        min_length=1,
    )

    has_restricted_information: bool | None = None
    coordinator_department_id: str | None = None

    goals: str | None = Field(
        default=None,
        min_length=1,
    )
    notes: str | None = None


# Дані, які FastAPI повертає клієнту.
class ProgramRead(ProgramBase):
    id: str

    model_config = ConfigDict(from_attributes=True)
