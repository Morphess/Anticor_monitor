from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    login: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Роль користувача: ADMIN, MAIN_KOORD, KOORD,
    # VYK, KER або ANAL.
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id"),
        nullable=False,
    )

    # Програма користувача (необов'язковий зв'язок).
    program_id: Mapped[str | None] = mapped_column(
        ForeignKey("programs.id"),
        nullable=True,
    )

    # Підрозділ користувача.
    department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id"),
        nullable=True,
    )

    position: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Зв'язок із роллю.
    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="users",
    )

    # Зв'язок із програмою.
    # Явно вказуємо зовнішній ключ, щоб SQLAlchemy
    # не плутав users.program_id із
    # programs.created_by_user_id.
    program: Mapped["Program | None"] = relationship(
        "Program",
        back_populates="users",
        foreign_keys=[program_id],
    )

    # Зв'язок із підрозділом.
    department: Mapped["Department | None"] = relationship(
        "Department",
        back_populates="users",
    )
