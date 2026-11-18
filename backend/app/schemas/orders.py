from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Основні поля наказу
class OrderBase(BaseModel):

    # Реєстраційний номер наказу
    number: str = Field(min_length=1, max_length=150)

    # Назва або тема наказу
    title: str = Field(min_length=1)

    # Дата видання
    issued_on: date | None = None

    # Посилання або шлях до документа
    document_url: str | None = Field(default=None, min_length=1)

    # ID заходу, до якого належить наказ
    measure_id: str = Field(min_length=1, max_length=8)

    @field_validator("number", "title", "measure_id")
    @classmethod
    def nonempty_text(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError("Поле не може містити лише пробіли")

        return value


# CREATE — створення наказу
class OrderCreate(OrderBase):

    id: str = Field(min_length=1, max_length=50)

    @field_validator("id")
    @classmethod
    def nonempty_id(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError("ID не може містити лише пробіли")

        return value


# UPDATE — часткове редагування
class OrderUpdate(BaseModel):

    number: str | None = Field(default=None, min_length=1, max_length=150)

    title: str | None = Field(default=None, min_length=1)

    issued_on: date | None = None

    document_url: str | None = Field(default=None, min_length=1)

    measure_id: str | None = Field(default=None, min_length=1, max_length=8)

    @field_validator("number", "title", "measure_id")
    @classmethod
    def nonempty_text(cls, value: str | None) -> str | None:

        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Поле не може містити лише пробіли")

        return value


# READ — відповідь API
class OrderRead(OrderBase):

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime

class OrderAnalysisRead(BaseModel):
    order_id: str
    file_name: str
    model: str
    analysis: str
    text_truncated: bool
