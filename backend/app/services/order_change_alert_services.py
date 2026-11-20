"""In-app повідомлення тільки для MAIN_KOORD/KOORD з доступом до заходу."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.order_change_alert import OrderChangeAlert, OrderChangeAlertRead
from app.models.order_version import OrderVersion
from app.models.order import Order
from app.models.execution import Execution
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError
from app.schemas.order_versions import (AlertCounter, AlertAcknowledgement,
                                        OrderChangeAlertReadSchema)
from app.services.measure_access import visible_measure_ids, require_visible_measure
from app.services.order_services import OrderError


class OrderChangeAlertService:
    def __init__(self, db: Session):
        self.db = db

    def require_alert(self, alert_id: int, actor) -> OrderChangeAlert:
        if actor.role_id not in {"KOORD", "MAIN_KOORD"}:
            raise OrderError("Повідомлення доступні тільки координаторам", 403)
        alert = self.db.get(OrderChangeAlert, alert_id)
        if alert is None:
            raise OrderError("Повідомлення не знайдено", 404)
        # Ця перевірка забороняє доступ до чужого заходу навіть по прямому ID.
        require_visible_measure(self.db, actor, alert.measure_id)
        if not self._visible(alert, actor):
            raise OrderError("Немає доступу до повідомлень цього підрозділу", 403)
        return alert

    def _visible(self, alert: OrderChangeAlert, actor) -> bool:
        if actor.role_id == "MAIN_KOORD":
            return True  # require_visible_measure already checks program ownership
        if not actor.department_id:
            return False
        row = self.db.get(Execution, alert.execution_id)
        department_id = row.submitted_department_id if row else None
        if department_id is None:
            return False
        try:
            return ProgramWorkflowService(self.db).tree.is_within(
                department_id, actor.department_id)
        except WorkflowError as exc:
            raise OrderError(exc.detail, exc.status_code) from exc

    def _read(self, alert: OrderChangeAlert, actor, read_ids: set[int]) -> OrderChangeAlertReadSchema:
        old = self.db.get(OrderVersion, alert.previous_version_id)
        new = self.db.get(OrderVersion, alert.new_version_id)
        order = self.db.get(Order, alert.order_id)
        execution = self.db.get(Execution, alert.execution_id)
        return OrderChangeAlertReadSchema(
            id=alert.id,
            execution_id=alert.execution_id,
            execution_measure_id=execution.measure_id,
            execution_period=execution.period,
            submitted_by_user_id=execution.submitted_by_user_id,
            measure_id=alert.measure_id,
            order_id=alert.order_id, order_number=order.number,
            previous_version_id=old.id, previous_version_number=old.version,
            previous_sha256=old.sha256,
            new_version_id=new.id, new_version_number=new.version,
            new_sha256=new.sha256,
            has_approved_execution=alert.has_approved_execution,
            created_at=alert.created_at, is_read=alert.id in read_ids,
        )

    def list_alerts(self, actor, *, program_id: str | None, unread_only: bool,
                    skip: int, limit: int) -> AlertCounter:
        if actor.role_id not in {"KOORD", "MAIN_KOORD"}:
            raise OrderError("Повідомлення доступні тільки координаторам", 403)
        ids = visible_measure_ids(self.db, actor, program_id)
        if not ids:
            return AlertCounter(total=0, unread=0, alerts=[])
        events = [alert for alert in self.db.scalars(
            select(OrderChangeAlert).where(OrderChangeAlert.measure_id.in_(ids))
            .order_by(OrderChangeAlert.created_at.desc(), OrderChangeAlert.id.desc())
        ) if self._visible(alert, actor)]
        if not events:
            return AlertCounter(total=0, unread=0, alerts=[])
        read_ids = set(self.db.scalars(
            select(OrderChangeAlertRead.alert_id).where(
                OrderChangeAlertRead.user_id == actor.id,
                OrderChangeAlertRead.alert_id.in_({event.id for event in events}),
            )
        ))
        unread = sum(event.id not in read_ids for event in events)
        filtered = [event for event in events if not unread_only or event.id not in read_ids]
        return AlertCounter(
            total=len(events), unread=unread,
            alerts=[self._read(event, actor, read_ids) for event in filtered[skip:skip + limit]],
        )

    def acknowledge(self, alert_id: int, actor) -> AlertAcknowledgement:
        alert = self.require_alert(alert_id, actor)
        if self.db.get(OrderChangeAlertRead, (alert.id, actor.id)) is None:
            self.db.add(OrderChangeAlertRead(alert_id=alert.id, user_id=actor.id))
            self.db.commit()
        return AlertAcknowledgement(alert_id=alert_id, is_read=True)
