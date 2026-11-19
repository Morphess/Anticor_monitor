"""Читання даних для Risk Flags у межах ОДНІЄЇ програми та дозволених заходів.

Умови доступу та дерево підрозділів визначає API через ProgramWorkflowService.
Цей репозиторій нічого не змінює в базі даних.

Важливо для RF7d: навіть коли координатор не бачить усі заходи,
наявність заходів за ризиком перевіряється по ВСІЙ програмі, аби не
повідомляти хибно про «ризик без заходів».
"""
from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.deadline_change import DeadlineChange
from app.models.evidence import Evidence
from app.models.invalid_order_reference import InvalidOrderReference
from app.models.execution import Execution
from app.models.measure import Measure
from app.models.risk import Risk
from app.models.risk_measurement import RiskMeasurement


class RiskFlagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def snapshot(
        self,
        *,
        program_id: str,
        period: str,
        period_start: date,
        period_end: date,
        as_of: date,
        visible_measure_ids: Collection[str],
        # None = власник MAIN_KOORD: усі ризики програми.
        # set(...) = KOORD: ризики його підрозділу/нащадків або доступних заходів.
        allowed_risk_department_ids: Collection[str] | None,
    ) -> dict[str, list[Any]]:
        """Повертає набори для detect_risk_flags() без сторонніх записів.

        Нуль дозволених заходів — допустима ситуація. У власника програми
        RF7d усе одно може спрацювати на ризику без заходів.
        """
        # Кожен отриманий захід додатково обмежений program_id на рівні SQL.
        measures = list(self.db.scalars(
            select(Measure)
            .where(Measure.program_id == program_id, Measure.id.in_(visible_measure_ids))
            .order_by(Measure.id)
        ))
        measure_ids = {m.id for m in measures}
        linked_risk_ids = {m.risk_id for m in measures if m.risk_id is not None}

        # ЄДИНА вибірка за всіма заходами програми. Не повертає чужі заходи,
        # потрібна лише для відповіді «ризик має хоча б один захід?».
        covered_risk_ids = set(self.db.scalars(
            select(Measure.risk_id).where(
                Measure.program_id == program_id,
                Measure.risk_id.is_not(None),
            )
        ))

        risk_query = select(Risk).where(Risk.program_id == program_id)
        if allowed_risk_department_ids is not None:
            risk_query = risk_query.where(or_(
                Risk.owner_department_id.in_(allowed_risk_department_ids),
                Risk.id.in_(linked_risk_ids),
            ))

        candidates = list(self.db.scalars(risk_query.order_by(Risk.id)))

        # Якщо ризик має захід, але цей захід НЕ видимий координатору,
        # НЕ передаємо такий ризик детектору — інакше RF7d буде хибним.
        # Ризики без жодного заходу передаємо (RF7d); для KOORD лише
        # якщо ризик належить його гілці завдяки умові вище.
        risks = [
            risk for risk in candidates
            if risk.id in linked_risk_ids or risk.id not in covered_risk_ids
        ]
        risk_ids = {risk.id for risk in risks}

        executions = list(self.db.scalars(
            select(Execution).where(
                Execution.measure_id.in_(measure_ids),
                Execution.period == period,
            )
        ))
        # Дата завантаження доказу додатково перевіряється детектором.
        evidences = list(self.db.scalars(
            select(Evidence).where(Evidence.measure_id.in_(measure_ids))
        ))
        deadline_changes = list(self.db.scalars(
            select(DeadlineChange).where(
                DeadlineChange.measure_id.in_(measure_ids),
                DeadlineChange.decision_date <= as_of,
            )
        ))
        measurements = list(self.db.scalars(
            select(RiskMeasurement).where(
                RiskMeasurement.risk_id.in_(risk_ids),
                RiskMeasurement.measured_on >= period_start,
                RiskMeasurement.measured_on <= period_end,
            )
        ))

        # Тільки відхилені спроби у доступних заходах і в звітному півріччі.
        # Верхня межа не включена, щоб охопити весь останній день.
        from_dt = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        to_dt = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        invalid_order_attempts = list(self.db.scalars(
            select(InvalidOrderReference).where(
                InvalidOrderReference.measure_id.in_(measure_ids),
                InvalidOrderReference.attempted_at >= from_dt,
                InvalidOrderReference.attempted_at < to_dt,
            )
        ))

        return {
            "invalid_order_attempts": invalid_order_attempts,
            "measures": measures,
            "executions": executions,
            "evidences": evidences,
            "deadline_changes": deadline_changes,
            "risks": risks,
            "measurements": measurements,
        }
