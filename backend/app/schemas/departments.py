"""Вхідні/вихідні схеми підрозділів із підтримкою ієрархії parent_id."""
from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1)
    department_type: str = Field(min_length=1, max_length=50)
    notes: str = ""
<<<<<<< HEAD
    # None означає кореневий підрозділ.
=======
    # Підпорядкованість: код вищого підрозділу; None — верхній рівень.
>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7
    parent_id: str | None = Field(default=None, min_length=1, max_length=10)


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    department_type: str | None = Field(default=None, min_length=1, max_length=50)
    notes: str | None = None
<<<<<<< HEAD
    # Поле можна не передавати (не змінювати) або передати null (зробити кореневим).
=======
    # null — зробити підрозділ верхнього рівня.
>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7
    parent_id: str | None = Field(default=None, min_length=1, max_length=10)


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    department_type: str
    notes: str
<<<<<<< HEAD
    parent_id: str | None


class DepartmentTreeRead(DepartmentRead):
    children: list["DepartmentTreeRead"] = Field(default_factory=list)


DepartmentTreeRead.model_rebuild()
=======
    parent_id: str | None = None
>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7
