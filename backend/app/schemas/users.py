from pydantic import BaseModel, ConfigDict, Field


# Дані для створення користувача
class UserCreate(BaseModel):

    login: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")

    password: str = Field(min_length=12, max_length=128)

    role_id: str = Field(min_length=1, max_length=10)

    program_id: str | None = None
    department_id: str | None = None
    position: str | None = None


# Дані для редагування користувача
class UserUpdate(BaseModel):

    login: str | None = Field(
        default=None, min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$"
    )

    password: str | None = Field(default=None, min_length=12, max_length=128)

    role_id: str | None = None
    program_id: str | None = None
    department_id: str | None = None
    position: str | None = None


# Дані, які API повертає клієнту
class UserRead(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    role_id: str
    program_id: str | None
    department_id: str | None
    position: str | None


# Дані для прив'язки користувача до програми
class UserProgramAssign(BaseModel):

    program_id: str | None = Field(
        ...,
        min_length=1,
        max_length=50,
        description=("Код антикорупційної програми " "або null для відв'язування"),
    )
