"""Вхідні/вихідні схеми підрозділів із підтримкою ієрархії parent_id."""
from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1)
    department_type: str = Field(min_length=1, max_length=50)
    notes: str = ""
    # None означає кореневий підрозділ.
    parent_id: str | None = Field(default=None, min_length=1, max_length=10)


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    department_type: str | None = Field(default=None, min_length=1, max_length=50)
    notes: str | None = None
    # Поле можна не передавати (не змінювати) або передати null (зробити кореневим).
    parent_id: str | None = Field(default=None, min_length=1, max_length=10)


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    department_type: str
    notes: str
    parent_id: str | None


class DepartmentTreeRead(DepartmentRead):
    children: list["DepartmentTreeRead"] = Field(default_factory=list)


DepartmentTreeRead.model_rebuild()
