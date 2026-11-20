from __future__ import annotations
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Довідник системних ролей та опису їхніх повноважень.
class Role(Base):
    __tablename__ = "roles"

    # Код ролі: ADMIN, KOORD, VYK, KER або ANAL.
    id: Mapped[str] = mapped_column(
        String(10), primary_key=True
    )  # ADMIN / KOORD / VYK / KER / ANAL
    # Людинозрозуміла назва ролі.
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Список облікових записів із цією роллю.
    users: Mapped[list["User"]] = relationship("User", back_populates="role")
