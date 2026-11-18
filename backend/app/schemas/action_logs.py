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
