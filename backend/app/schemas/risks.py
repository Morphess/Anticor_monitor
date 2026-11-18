from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Основні дані корупційного ризику
class RiskBase(BaseModel):

    process_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)

    risk_sources: str = Field(min_length=1)
    existing_controls: str = Field(min_length=1)

    probability_score: int = Field(ge=1, le=4)
    impact_score: int = Field(ge=1, le=4)
    score: int = Field(ge=1, le=16)

    level: Literal["low", "medium", "high", "critical"]

    owner_department_id: str | None = Field(default=None, max_length=8)

    indicator_name: str = Field(min_length=1)
    indicator_unit: str = Field(min_length=1, max_length=20)

    indicator_direction: Literal["increase", "decrease"]

    indicator_baseline_value: Decimal = Field(max_digits=14, decimal_places=3)

    indicator_target_value: Decimal = Field(max_digits=14, decimal_places=3)

    target_date: date

    # Перевіряємо правильність розрахунку балів
    @model_validator(mode="after")
    def check_score(self):

        expected_score = self.probability_score * self.impact_score

        if self.score != expected_score:
            raise ValueError(
                f"Неправильний бал ризику. " f"Очікується {expected_score}"
            )

        return self


# Створення нового ризику
class RiskCreate(RiskBase):

    id: str = Field(min_length=1, max_length=8)


# Часткове редагування ризику
class RiskUpdate(BaseModel):

    process_name: str | None = Field(default=None, min_length=1)

    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)

    risk_sources: str | None = Field(default=None, min_length=1)

    existing_controls: str | None = Field(default=None, min_length=1)

    probability_score: int | None = Field(default=None, ge=1, le=4)

    impact_score: int | None = Field(default=None, ge=1, le=4)

    score: int | None = Field(default=None, ge=1, le=16)

    level: Literal["low", "medium", "high", "critical"] | None = None

    owner_department_id: str | None = Field(default=None, max_length=8)

    indicator_name: str | None = Field(default=None, min_length=1)

    indicator_unit: str | None = Field(default=None, min_length=1, max_length=20)

    indicator_direction: Literal["increase", "decrease"] | None = None

    indicator_baseline_value: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3
    )

    indicator_target_value: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=3
    )

    target_date: date | None = None


# Відповідь API
class RiskRead(RiskBase):

    model_config = ConfigDict(from_attributes=True)

    id: str
