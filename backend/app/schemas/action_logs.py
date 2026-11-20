from datetime import datetime

from pydantic import BaseModel, ConfigDict


# Запис журналу дій
class ActionLogRead(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: str
    occurred_at: datetime
    actor_user_id: int | None

    action: str

    entity_type: str
    entity_id: str

    field_name: str | None
    old_value: str | None
    new_value: str | None


# ---------- Журнал дій для кабінету адміністратора ----------

class ActionLogActor(BaseModel):
    """Хто виконав дію: обліковий запис і його поточний підрозділ."""

    id: int
    login: str
    role_id: str
    position: str | None = None
    department_id: str | None = None
    department_name: str | None = None


class ActionLogFeedItem(BaseModel):
    id: str
    occurred_at: datetime  # UTC
    actor: ActionLogActor | None  # None — системна дія без користувача
    action: str
    entity_type: str
    entity_id: str
    field_name: str | None
    old_value: str | None
    new_value: str | None


class ActionLogFeedPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ActionLogFeedItem]


class ActionLogFacets(BaseModel):
    """Значення для фільтрів: які дії та об'єкти реально є в журналі."""

    actions: list[str]
    entity_types: list[str]
