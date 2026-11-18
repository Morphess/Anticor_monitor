from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# Основні поля підтвердного документа
class EvidenceBase(BaseModel):

    # Захід, до якого належить документ
    measure_id: str = Field(min_length=1, max_length=8)

    # Тип документа
    document_type: str = Field(min_length=1, max_length=50)

    # Назва документа
    title: str = Field(min_length=1)

    # Дата документа
    document_date: date | None = None

    # Посилання на документ
    source_url: str | None = None

    # SHA-256 у вигляді 64 шістнадцяткових символів
    reference_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


# Створення документа
class EvidenceCreate(EvidenceBase):

    id: str = Field(min_length=1, max_length=12)


# Часткове редагування документа
class EvidenceUpdate(BaseModel):

    measure_id: str | None = Field(default=None, min_length=1, max_length=8)

    document_type: str | None = Field(default=None, min_length=1, max_length=50)

    title: str | None = Field(default=None, min_length=1)

    document_date: date | None = None

    source_url: str | None = None

    reference_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


# Дані, які повертає API
class EvidenceRead(EvidenceBase):

    model_config = ConfigDict(from_attributes=True)

    id: str
    uploaded_at: datetime
