"""Immutable order revisions, alerts tied to executions, and invalidation on changes."""
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.execution import Execution
from app.models.order import Order
from app.models.order_change_alert import OrderChangeAlert
from app.models.order_version import OrderVersion
from app.services.order_document_storage import DocumentStorageError, OrderDocumentStorage
from app.services.order_services import OrderError


class OrderVersionService:
    def __init__(self, db: Session, storage: OrderDocumentStorage | None = None):
        self.db = db
        self.storage = storage or OrderDocumentStorage()

    def get(self, version_id: int) -> OrderVersion:
        obj = self.db.get(OrderVersion, version_id)
        if obj is None:
            raise OrderError("Версію наказу не знайдено", 404)
        return obj

    def latest(self, order_id: str) -> OrderVersion | None:
        return self.db.scalar(select(OrderVersion).where(OrderVersion.order_id == order_id)
                              .order_by(OrderVersion.version.desc()).limit(1))

    def list_versions(self, order_id: str) -> list[OrderVersion]:
        if self.db.get(Order, order_id) is None:
            raise OrderError("Наказ не знайдено", 404)
        return list(self.db.scalars(select(OrderVersion).where(OrderVersion.order_id == order_id)
                                    .order_by(OrderVersion.version)))

    def upload(self, order_id: str, upload: UploadFile, change_reason: str,
               *, operator_user_id: int | None = None) -> OrderVersion:
        if not change_reason or not change_reason.strip():
            raise OrderError("Вкажи причину або опис зміни", 422)
        order = self.db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            raise OrderError("Наказ не знайдено", 404)
        old = self.latest(order_id)
        if old:
            try:
                self.storage.verify(old)
            except DocumentStorageError as exc:
                self.db.rollback()
                raise OrderError(str(exc), 409) from exc
        try:
            staged, meta = self.storage.stage(upload)
        except DocumentStorageError as exc:
            self.db.rollback()
            raise OrderError(str(exc), 422) from exc
        except Exception:
            self.db.rollback()
            raise

        target: Path | None = None
        try:
            if old and old.sha256 == meta["sha256"]:
                raise OrderError("Вміст збігається з попередньою версією", 409)
            target = self.storage.finalize(staged, meta["storage_key"])
            version = OrderVersion(
                order_id=order_id, version=old.version + 1 if old else 1,
                change_reason=change_reason.strip(), uploaded_by_user_id=operator_user_id,
                **meta,
            )
            self.db.add(version)
            self.db.flush()
            # Stable protected registry link; actual bytes served by authenticated API.
            order.document_url = f"/api/orders/{order.id}/document"
            if old:
                executions = list(self.db.scalars(select(Execution)
                                                  .where(Execution.order_id == order_id,
                                                         Execution.order_version_id.is_not(None))
                                                  .with_for_update()))
                for execution in executions:
                    if execution.order_version_id == version.id:
                        continue
                    existing_alert = self.db.scalar(select(OrderChangeAlert.id).where(
                        OrderChangeAlert.execution_id == execution.id,
                        OrderChangeAlert.new_version_id == version.id,
                    ).limit(1))
                    if existing_alert:
                        continue
                    was_approved = execution.status == "approved"
                    self.db.add(OrderChangeAlert(
                        execution_id=execution.id,
                        measure_id=execution.measure_id,
                        order_id=order_id,
                        previous_version_id=execution.order_version_id,
                        new_version_id=version.id,
                        has_approved_execution=was_approved,
                    ))
                    execution.document_changed = True
                    if was_approved:
                        execution.status = "pending"
                        execution.approved_by_coordinator = False
                        # Historic reviewer decision remains in immutable action_logs.
                        execution.reviewed_by_user_id = None
                        execution.reviewed_at = None
                    execution.status_label = "Наказ оновлено: потрібне повторне подання"
            self.db.commit()
            self.db.refresh(version)
            return version
        except OrderError:
            self.db.rollback()
            (target or staged).unlink(missing_ok=True)
            raise
        except IntegrityError as exc:
            self.db.rollback()
            (target or staged).unlink(missing_ok=True)
            raise OrderError("Конфлікт паралельних версій наказу", 409) from exc
        except Exception:
            self.db.rollback()
            (target or staged).unlink(missing_ok=True)
            raise
