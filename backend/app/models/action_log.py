"""Аудит: entity_id не FK, бо різні entity_type посилаються на різні таблиці."""

from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


# Аудит дій користувачів: зберігаємо, хто, коли та що змінив.
class ActionLog(Base):
    # Ім’я таблиці в PostgreSQL, з якою працює ця модель.
    __tablename__ = "action_logs"

    # Унікальний ID події (демо L-0001; для нових подій можна використовувати UUID).
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )  # L-0001 (demo); UUID for new events
    # Дата і час дії; часовий пояс тут не зберігається, бо його немає у вхідних даних.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
    # Реальний користувач застосунку, який виконав дію; необов’язковий зв’язок.
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Текст дії: створив запис, змінив статус, додав підтвердження тощо.
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # Тип об’єкта, якого стосується дія (measure/execution/evidence).
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # ID конкретного об’єкта; це не FK, адже об’єкти лежать у різних таблицях.
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # Назва поля, яке було змінено; може не заповнюватися.
    field_name: Mapped[str | None] = mapped_column(String(100))
    # Попереднє значення зміненого поля; може бути порожнім.
    old_value: Mapped[str | None] = mapped_column(Text)
    # Нове значення зміненого поля; може бути порожнім.
    new_value: Mapped[str | None] = mapped_column(Text)

    # ORM-доступ до об’єкта User через actor_user_id.
    actor_user: Mapped["User | None"] = relationship("User")
