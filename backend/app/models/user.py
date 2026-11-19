from __future__ import annotations
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Справжній обліковий запис для входу в FastAPI.
class User(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "users"

    # Автоматично згенерований числовий ID облікового запису.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Унікальний логін користувача, індексований для швидкого пошуку.
    login: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    # Безпечно обчислений хеш пароля; ніколи не зберігай відкритий пароль.
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Argon2/bcrypt, NOT plaintext
    # Код системної ролі (FK → roles.id).
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    # Програма користувача; може бути NULL для загальносистемного адміністратора.
    program_id: Mapped[str | None] = mapped_column(
        ForeignKey("programs.id"), nullable=True
    )
    # Підрозділ користувача; необов’язково.
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    # Посада користувача; необов’язково.
    position: Mapped[str | None] = mapped_column(Text)

    # ORM-доступ до ролі користувача (об’єкт Role).
    role: Mapped["Role"] = relationship("Role", back_populates="users")
    # ORM-доступ до програми користувача (об’єкт Program).
    program: Mapped["Program | None"] = relationship(
        "Program",
        back_populates="users",
        foreign_keys=[program_id],
    )

    # ORM-доступ до підрозділу користувача (об’єкт Department).
    department: Mapped["Department | None"] = relationship(
        "Department", back_populates="users"
    )
