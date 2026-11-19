"""Додавання незмінних версій файлу наказу та формування повідомлень."""
from __future__ import annotations
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
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
        return self.db.scalar(
            select(OrderVersion)
            .where(OrderVersion.order_id == order_id)
            .order_by(OrderVersion.version.desc()).limit(1)
        )

    def list_versions(self, order_id: str) -> list[OrderVersion]:
        if self.db.get(Order, order_id) is None:
            raise OrderError("Наказ не знайдено", 404)
        return list(self.db.scalars(
            select(OrderVersion)
            .where(OrderVersion.order_id == order_id)
            .order_by(OrderVersion.version)
        ))

    def upload(self, order_id: str, upload: UploadFile, change_reason: str,
               *, operator_user_id: int | None = None) -> OrderVersion:
        if not change_reason or not change_reason.strip():
            raise OrderError("Вкажи причину/опис зміни", 422)
        # Рядок наказу блокуємо в PostgreSQL від паралельної нумерації версій.
        order = self.db.scalar(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        if order is None:
            raise OrderError("Наказ не знайдено", 404)
        old = self.latest(order_id)
        if old is not None:
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
            if old is not None and old.sha256 == meta["sha256"]:
                raise OrderError("Файл збігається з поточною версією: змін немає", 409)

            target = self.storage.finalize(staged, meta["storage_key"])
            version = OrderVersion(
                order_id=order_id,
                version=(old.version + 1) if old is not None else 1,
                change_reason=change_reason.strip(),
                uploaded_by_user_id=operator_user_id,
                **meta,
            )
            self.db.add(version)
            self.db.flush()  # отримуємо ID до створення повідомлень
            if old is not None:
                # Усі підтвердження, прив'язані до попередніх версій цього наказу.
                evidences = list(self.db.scalars(
                    select(Evidence)
                    .join(OrderVersion, Evidence.order_version_id == OrderVersion.id)
                    .where(OrderVersion.order_id == order_id)
                ))
                approved_ids = set(self.db.scalars(
                    select(Execution.measure_id).where(
                        Execution.measure_id.in_({e.measure_id for e in evidences}),
                        Execution.approved_by_coordinator.is_(True),
                    )
                )) if evidences else set()
                for evidence in evidences:
                    self.db.add(OrderChangeAlert(
                        evidence_id=evidence.id,
                        measure_id=evidence.measure_id,
                        order_id=order_id,
                        previous_version_id=evidence.order_version_id,
                        new_version_id=version.id,
                        has_approved_execution=evidence.measure_id in approved_ids,
                    ))
            self.db.commit()
            self.db.refresh(version)
            return version
        except OrderError:
            self.db.rollback()
            if target is not None:
                target.unlink(missing_ok=True)
            else:
                staged.unlink(missing_ok=True)
            raise
        except IntegrityError as exc:
            self.db.rollback()
            if target is not None:
                target.unlink(missing_ok=True)
            else:
                staged.unlink(missing_ok=True)
            raise OrderError("Конфлікт версій: повтори завантаження", 409) from exc
        except Exception:
            self.db.rollback()
            if target is not None:
                target.unlink(missing_ok=True)
            else:
                staged.unlink(missing_ok=True)
            raise
