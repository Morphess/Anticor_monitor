from pydantic import BaseModel


class RiskFlagRead(BaseModel):
    """Знайдений сигнал; назви об'єктів відповідають dictionary.md."""

    code: str
    object_type: str  # zakhid / pidrozdil / ryzyk
    object_id: str
    period: str
    message: str
    explanation: str
