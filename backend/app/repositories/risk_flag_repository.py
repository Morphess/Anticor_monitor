"""Збір даних для правил RF1–RF7e. Читання без жодних змін у БД."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deadline_change import DeadlineChange
from app.models.evidence import Evidence
from app.models.execution import Execution
from app.models.measure import Measure
from app.models.risk import Risk
from app.models.risk_measurement import RiskMeasurement


class RiskFlagRepository:
    def __init__(self, db: Session):
        self.db = db

    def snapshot(self, *, period: str, period_end: date, as_of: date) -> dict:
        """Стан документів і рішень на кінець дати зрізу."""
        as_of_exclusive = datetime.combine(as_of + timedelta(days=1), time.min)
        return {
            "measures": list(self.db.scalars(select(Measure)).all()),
            "executions": list(self.db.scalars(
                select(Execution).where(Execution.period == period)
            ).all()),
            "evidences": list(self.db.scalars(
                select(Evidence).where(Evidence.uploaded_at < as_of_exclusive)
            ).all()),
            "deadline_changes": list(self.db.scalars(
                select(DeadlineChange).where(DeadlineChange.decision_date <= as_of)
            ).all()),
            "risks": list(self.db.scalars(select(Risk)).all()),
            "measurements": list(self.db.scalars(
                select(RiskMeasurement).where(RiskMeasurement.measured_on <= period_end)
            ).all()),
        }
