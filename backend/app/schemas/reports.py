from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReportStatus = Literal["draft", "generated", "submitted"]


# Створення запису про звіт
class ReportCreate(BaseModel):

    # Програма, до якої належить звіт
    program_id: str = Field(min_length=1, max_length=50)

    # Звітний період, наприклад 2026-H1
    period: str = Field(min_length=1, max_length=20)

    # Номер версії
    version: int = Field(default=1, ge=1)

    # Файл звіту, якщо вже існує
    export_file_path: str | None = Field(default=None, min_length=1)


# Редагування запису про звіт
class ReportUpdate(BaseModel):

    # Статус звіту
    status: ReportStatus | None = None

    # Шлях до експортованого файлу
    export_file_path: str | None = Field(default=None, min_length=1)


# Дані, які повертає API
class ReportRead(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    program_id: str
    period: str
    version: int
    status: ReportStatus
    generated_at: datetime
    generated_by_user_id: int | None
    export_file_path: str | None
