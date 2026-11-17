from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Основні дані про перенесення строку
class DeadlineChangeBase(BaseModel):

    # Код заходу, наприклад Z-01
    measure_id: str = Field(min_length=1, max_length=8)

    # Дата ухвалення рішення
    decision_date: date

    # Попередній строк
    previous_deadline: date

    # Новий строк
    new_deadline: date

    # Причина перенесення
    reason: str = Field(min_length=1)

    # Новий строк має бути пізніше попереднього
    @model_validator(mode="after")
    def check_dates(self):
        if self.new_deadline <= self.previous_deadline:
            raise ValueError("Новий строк має бути пізніше попереднього")
        return self


# Створення рішення
class DeadlineChangeCreate(DeadlineChangeBase):
    pass


# Часткове редагування
class DeadlineChangeUpdate(BaseModel):

    decision_date: date | None = None
    previous_deadline: date | None = None
    new_deadline: date | None = None
    reason: str | None = Field(default=None, min_length=1)


# Дані, які повертає API
class DeadlineChangeRead(DeadlineChangeBase):

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
