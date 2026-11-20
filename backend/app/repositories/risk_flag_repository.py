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
from types import SimpleNamespace
from app.models.order import Order
from app.models.order_version import OrderVersion
from app.services.execution_summary import summaries, assignments_for

from app.models.deadline_change import DeadlineChange
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

        # Program-level risks come only from measures of this program.
        # RF7d also sees truly orphaned global risks in the permitted department
        # (never risks merely assigned to another program).
        global_covered = select(Measure.risk_id).where(Measure.risk_id.is_not(None))
        if allowed_risk_department_ids is None:
            risk_query = select(Risk).where(Risk.id.in_(covered_risk_ids))
        else:
            owned_uncovered = (
                Risk.owner_department_id.in_(allowed_risk_department_ids)
                & ~Risk.id.in_(global_covered)
            )
            risk_query = select(Risk).where(or_(Risk.id.in_(covered_risk_ids), owned_uncovered))
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
        # Risk Flags work on one aggregated measure status, never an arbitrary executor.
        aggregate = summaries(self.db, measure_ids, period, executions)
        active = assignments_for(self.db, measure_ids)
        # Доказ для Risk Flags утворюється з погодженого виконання та версії наказу.
        confirmed_orders = []
        for submission in executions:
            if (submission.status != "approved" or submission.document_changed
                    or submission.submitted_by_user_id not in active.get(submission.measure_id, set())):
                continue
            if submission.order_version_id is None or submission.order_id is None:
                continue
            version = self.db.get(OrderVersion, submission.order_version_id)
            order = self.db.get(Order, submission.order_id)
            if version is None or order is None or version.sha256 != submission.submitted_sha256:
                continue
            confirmed_orders.append(SimpleNamespace(
                measure_id=submission.measure_id,
                submitted_at=submission.submitted_at,
                document_date=order.issued_on,
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
            "executions": list(aggregate.values()),
            "confirmed_orders": confirmed_orders,
            "deadline_changes": deadline_changes,
            "risks": risks,
            "measurements": measurements,
        }
