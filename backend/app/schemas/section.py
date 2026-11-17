from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


SectionId = Literal["R1", "R2", "R3"]


class SectionCreate(BaseModel):
    id: SectionId
    number: int = Field(ge=1, le=3)
    title: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_id_number(self):
        expected_id = f"R{self.number}"

        if self.id != expected_id:
            raise ValueError(
                f"Розділ №{self.number} повинен мати " f"код {expected_id}"
            )

        return self


class SectionUpdate(BaseModel):
    # Код і номер розділу не редагуються.
    title: str = Field(min_length=1)


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    number: int
    title: str
