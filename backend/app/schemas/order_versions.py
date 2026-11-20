"""Order version and execution alert API models."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class OrderVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: str
    version: int
    sha256: str
    original_filename: str
    content_type: str
    size_bytes: int
    change_reason: str
    created_at: datetime
    uploaded_by_user_id: int | None


class OrderChangeAlertReadSchema(BaseModel):
    id: int
    execution_id: int
    execution_measure_id: str
    execution_period: str
    submitted_by_user_id: int | None = None
    measure_id: str
    order_id: str
    order_number: str
    previous_version_id: int
    previous_version_number: int
    previous_sha256: str
    new_version_id: int
    new_version_number: int
    new_sha256: str
    has_approved_execution: bool
    created_at: datetime
    is_read: bool


class AlertCounter(BaseModel):
    total: int
    unread: int
    alerts: list[OrderChangeAlertReadSchema]


class AlertAcknowledgement(BaseModel):
    alert_id: int
    is_read: bool
