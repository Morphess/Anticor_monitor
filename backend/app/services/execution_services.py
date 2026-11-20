"""Independent executor submissions with pinned SHA-256 order versions."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.execution import Execution
from app.models.action_log import ActionLog
from app.models.invalid_order_reference import InvalidOrderReference
from app.models.order import Order
from app.models.order_version import OrderVersion
from app.models.program_workflow import MeasureAssignment
from app.repositories.execution_repository import ExecutionRepository
from app.schemas.execution import ExecutionSubmit
from app.services.order_document_storage import OrderDocumentStorage, DocumentStorageError
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError


def utc_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExecutionError(Exception):
    def __init__(self, detail: str, status_code: int = 409):
        super().__init__(detail)
        self.status_code = status_code


class ExecutionService:
    def __init__(self, db: Session, storage: OrderDocumentStorage | None = None):
        self.db = db
        self.repo = ExecutionRepository(db)
        self.storage = storage or OrderDocumentStorage()

    def get(self, execution_id: int) -> Execution:
        row = self.repo.by_id(execution_id)
        if row is None:
            raise ExecutionError('Подання не знайдено', 404)
        return row

    def as_read(self, row: Execution):
        from app.schemas.execution import ExecutionRead
        order = self.db.get(Order, row.order_id) if row.order_id else None
        return ExecutionRead.model_validate(row).model_copy(update={
            'order_number': order.number if order else None,
            'document_api_path': f'/api/executions/{row.id}/document' if row.order_version_id else None,
        })

    def _require_coordinator(self, row: Execution, actor) -> None:
        if actor.role_id != 'KOORD' or not actor.department_id:
            raise ExecutionError('Погоджувати може тільки координатор підрозділу', 403)
        if row.submitted_by_user_id == actor.id:
            raise ExecutionError('Не можна погоджувати власне подання', 403)
        if not row.submitted_department_id:
            raise ExecutionError('У подання відсутній підрозділ виконавця', 409)
        try:
            accessible = ProgramWorkflowService(self.db).tree.is_within(
                row.submitted_department_id, actor.department_id
            )
        except WorkflowError as exc:
            raise ExecutionError(exc.detail, exc.status_code) from exc
        if not accessible:
            raise ExecutionError('Виконавець не належить до підрозділів координатора', 403)

    def require_read_access(self, row: Execution, actor) -> None:
        if actor.role_id == 'VYK' and row.submitted_by_user_id != actor.id:
            raise ExecutionError('Чуже подання недоступне', 403)
        if actor.role_id == 'KOORD':
            self._require_coordinator(row, actor)
        if actor.role_id not in {'MAIN_KOORD', 'KOORD', 'VYK'}:
            raise ExecutionError('Немає доступу', 403)

    def _order_and_version(self, number: str) -> tuple[Order, OrderVersion]:
        order = self.db.scalar(select(Order).where(Order.number == number).with_for_update())
        if order is None:
            raise ExecutionError('Наказ із таким номером не знайдено', 404)
        version = self.db.scalar(select(OrderVersion).where(OrderVersion.order_id == order.id)
                                 .order_by(OrderVersion.version.desc()).limit(1))
        if version is None:
            raise ExecutionError('Наказ є, але файл ще не завантажено', 409)
        try:
            self.storage.verify(version)
        except DocumentStorageError as exc:
            raise ExecutionError(str(exc), 409) from exc
        return order, version

    def submit(self, data: ExecutionSubmit, actor) -> Execution:
        if actor.role_id != 'VYK' or not actor.department_id:
            raise ExecutionError('Подання доступне тільки призначеному виконавцю', 403)
        assignment = self.db.get(MeasureAssignment, (data.measure_id, actor.id))
        if assignment is None or assignment.department_id != actor.department_id:
            raise ExecutionError('Немає чинного персонального призначення', 403)
        from app.services.measure_access import require_visible_measure
        require_visible_measure(self.db, actor, data.measure_id)
        number = data.order_number.strip()
        try:
            order, version = self._order_and_version(number)
        except ExecutionError as exc:
            if exc.status_code == 404:
                self.db.rollback()
                previous = self.repo.get(data.measure_id, data.period, actor.id)
                self.db.add(InvalidOrderReference(
                    id=str(uuid4()), measure_id=data.measure_id,
                    actor_user_id=actor.id, order_number=number,
                    action='update' if previous else 'create',
                ))
                self.db.commit()
            else:
                self.db.rollback()
            raise
        existing = self.repo.get(data.measure_id, data.period, actor.id, lock=True)
        if existing:
            if existing.status == 'approved' and not existing.document_changed:
                self.db.rollback()
                raise ExecutionError('Ваше виконання вже погоджено', 409)
            if existing.status == 'pending' and not existing.document_changed:
                self.db.rollback()
                raise ExecutionError('Ваше подання вже чекає рішення', 409)
            row = existing
        else:
            row = Execution(measure_id=data.measure_id, period=data.period,
                            submitted_by_user_id=actor.id)
            self.db.add(row)
        row.order_id = order.id
        row.order_version_id = version.id
        row.submitted_sha256 = version.sha256
        row.document_changed = False
        row.status = 'pending'
        row.submitted_department_id = assignment.department_id
        row.submitted_at = utc_naive()
        row.reviewed_by_user_id = None
        row.reviewed_at = None
        row.rejection_reason = None
        row.approved_by_coordinator = False
        # Дані для звіту НАЗК; враховуються лише після погодження координатором.
        completed_on = data.completed_on or utc_naive().date()
        if completed_on > utc_naive().date():
            self.db.rollback()
            raise ExecutionError('Фактична дата виконання не може бути в майбутньому', 422)
        row.outcome_status = data.outcome_status
        row.completed_on = completed_on
        row.result_description = data.result_description
        row.indicator_actual = data.indicator_actual
        row.status_label = 'Очікує погодження'
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ExecutionError('Ви вже подали виконання за цей період; оновіть сторінку', 409) from exc
        self.db.refresh(row)
        return row

    def change_order(self, execution_id: int, number: str, actor) -> Execution:
        """Replace own pending order; preserve execution id and append audit event.

        Only pending, unmodified submissions can be edited here. Rejected or
        invalidated submissions use the normal /submit workflow.
        """
        if actor.role_id != 'VYK' or not actor.department_id:
            raise ExecutionError('Змінювати наказ може тільки виконавець', 403)
        preliminary = self.get(execution_id)
        if preliminary.submitted_by_user_id != actor.id:
            raise ExecutionError('Чуже подання змінювати заборонено', 403)
        if preliminary.status != 'pending' or preliminary.document_changed:
            raise ExecutionError('Редагувати можна лише подання, що очікує погодження', 409)
        from app.services.measure_access import require_visible_measure
        require_visible_measure(self.db, actor, preliminary.measure_id)
        assignment = self.db.get(MeasureAssignment, (preliminary.measure_id, actor.id))
        if assignment is None or assignment.department_id != actor.department_id:
            raise ExecutionError('Призначення більше не чинне', 403)
        number = number.strip()
        if not number:
            raise ExecutionError('Вкажіть номер наказу', 422)
        try:
            order, version = self._order_and_version(number)
        except ExecutionError as exc:
            if exc.status_code == 404:
                self.db.rollback()
                self.db.add(InvalidOrderReference(
                    id=str(uuid4()), measure_id=preliminary.measure_id,
                    actor_user_id=actor.id, order_number=number, action='update',
                ))
                self.db.commit()
            else:
                self.db.rollback()
            raise

        row = self.repo.by_id(execution_id, lock=True)
        if (row is None or row.submitted_by_user_id != actor.id
                or row.status != 'pending' or row.document_changed):
            self.db.rollback()
            raise ExecutionError('Подання вже змінилося. Оновіть сторінку.', 409)
        if row.order_id == order.id:
            self.db.rollback()
            raise ExecutionError('Цей номер наказу вже вказано. Для зміни оберіть інший наказ.', 409)
        previous_order = self.db.get(Order, row.order_id) if row.order_id else None
        previous_number = previous_order.number if previous_order else '—'
        row.order_id = order.id
        row.order_version_id = version.id
        row.submitted_sha256 = version.sha256
        row.document_changed = False
        row.status = 'pending'  # The new order always needs a new review.
        row.submitted_at = utc_naive()
        row.submitted_department_id = assignment.department_id
        row.approved_by_coordinator = False
        row.reviewed_by_user_id = None
        row.reviewed_at = None
        row.rejection_reason = None
        row.status_label = 'Замінено наказ — очікує погодження'
        self.db.add(ActionLog(
            id=str(uuid4()), occurred_at=utc_naive(), actor_user_id=actor.id,
            action='change_order_number', entity_type='execution',
            entity_id=str(row.id), field_name='order_number',
            old_value=previous_number, new_value=order.number,
        ))
        self.db.commit()
        self.db.refresh(row)
        return row

    def _is_modified(self, row: Execution, *, latest: OrderVersion) -> bool:
        if row.order_version_id != latest.id or row.submitted_sha256 != latest.sha256:
            return True
        try:
            self.storage.verify(latest)
        except DocumentStorageError:
            return True
        return False

    def invalidate_if_changed(self, row: Execution) -> bool:
        if row.order_id is None or row.order_version_id is None:
            return True
        latest = self.db.scalar(select(OrderVersion).where(OrderVersion.order_id == row.order_id)
                                .order_by(OrderVersion.version.desc()).limit(1))
        changed = latest is None or self._is_modified(row, latest=latest)
        if changed:
            row.document_changed = True
            row.status = 'pending'
            row.approved_by_coordinator = False
            row.reviewed_by_user_id = None
            row.reviewed_at = None
            row.status_label = 'Наказ змінено — потрібне повторне подання'
        return changed

    def review(self, execution_id: int, actor, *, approve: bool, reason: str | None = None,
               expected_order_version_id: int | None = None, expected_submitted_at: datetime | None = None) -> Execution:
        preliminary = self.get(execution_id)
        if preliminary.order_id is None:
            raise ExecutionError('У поданні немає наказу', 409)
        # Lock order first, as in upload/submit; re-check row after acquiring lock.
        self.db.scalar(select(Order).where(Order.id == preliminary.order_id).with_for_update())
        row = self.repo.by_id(execution_id, lock=True)
        if row is None or row.order_id != preliminary.order_id:
            raise ExecutionError('Подання було змінено; оновіть сторінку', 409)
        self._require_coordinator(row, actor)
        # Prevent the coordinator from approving a newly substituted order using
        # an old, still-open review dialog.
        if ((expected_order_version_id is not None and row.order_version_id != expected_order_version_id)
                or (expected_submitted_at is not None and row.submitted_at != expected_submitted_at)):
            self.db.rollback()
            raise ExecutionError('Виконавець змінив подання. Перевірте новий наказ перед рішенням.', 409)
        assignment = self.db.get(MeasureAssignment, (row.measure_id, row.submitted_by_user_id))
        if assignment is None or assignment.department_id != row.submitted_department_id:
            raise ExecutionError('Призначення цього виконавця вже відкликано', 409)
        if row.status != 'pending':
            raise ExecutionError('Рішення доступне лише для pending', 409)
        if row.document_changed or self.invalidate_if_changed(row):
            self.db.commit()
            raise ExecutionError('Документ змінено. Потрібне повторне подання виконавця', 409)
        if not approve and (not reason or len(reason.strip()) < 3):
            raise ExecutionError('Причина відхилення має містити хоча б 3 символи', 422)
        row.status = 'approved' if approve else 'rejected'
        row.approved_by_coordinator = approve
        row.status_label = 'Погоджено' if approve else 'Відхилено'
        row.reviewed_by_user_id = actor.id
        row.reviewed_at = utc_naive()
        row.rejection_reason = None if approve else reason.strip()
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_document(self, row: Execution, actor, *, which: str = 'submitted'):
        self.require_read_access(row, actor)
        if row.order_id is None or row.order_version_id is None:
            raise ExecutionError('Документ не знайдено', 404)
        if which not in {'submitted', 'current'}:
            raise ExecutionError('Вкажіть submitted або current', 422)
        version = (self.db.scalar(select(OrderVersion).where(OrderVersion.order_id == row.order_id)
                                  .order_by(OrderVersion.version.desc()).limit(1))
                   if which == 'current' else self.db.get(OrderVersion, row.order_version_id))
        if version is None or version.order_id != row.order_id:
            raise ExecutionError('Версію наказу не знайдено', 404)
        try:
            path = self.storage.verify(version)
        except DocumentStorageError as exc:
            raise ExecutionError(str(exc), 409) from exc
        return path, version
