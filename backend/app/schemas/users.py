from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")

    password: str = Field(min_length=12, max_length=128)

    @field_validator("role_id")
    @classmethod
    def active_role(cls, value):
        if value == "ANAL":
            raise ValueError("Роль аналітика більше не використовується")
        return value

    role_id: str = Field(min_length=1, max_length=10)

    department_id: str | None = None
    position: str | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str | None = Field(
        default=None, min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$"
    )

    password: str | None = Field(default=None, min_length=12, max_length=128)

    @field_validator("role_id")
    @classmethod
    def active_role(cls, value):
        if value == "ANAL":
            raise ValueError("Роль аналітика більше не використовується")
        return value

    role_id: str | None = None
    department_id: str | None = None
    position: str | None = None


class UserRead(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    role_id: str
    program_id: str | None
    department_id: str | None
    position: str | None
