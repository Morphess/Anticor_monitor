"""Формати відповіді журналу дій. Не замінює наявні schemas/action_logs.py."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ActionLogActor(BaseModel):
    id: int
    login: str
    role_id: str
    position: str | None = None
    # Згідно з поточною моделлю User: FK departments.id має тип INTEGER.
    department_id: int | None = None
    department_name: str | None = None


class ActionLogFeedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    occurred_at: datetime  # UTC, без timezone у наявній таблиці
    actor: ActionLogActor | None = None
    action: str
    entity_type: str
    entity_id: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class ActionLogFeedPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ActionLogFeedItem]


class ActionLogFacets(BaseModel):
    actions: list[str]
    entity_types: list[str]
