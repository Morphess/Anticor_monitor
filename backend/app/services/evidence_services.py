"""Робота з підтвердженнями та звіряння номерів наказів з реєстром."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.invalid_order_reference import InvalidOrderReference
from app.models.measure import Measure
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidences import EvidenceCreate, EvidenceRead, EvidenceUpdate
from app.services.order_services import OrderService


class EvidenceError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class OrderReferenceNotFound(EvidenceError):
    """Вказаний номер наказу не знайдено у незалежному реєстрі orders."""

    def __init__(self, order_number: str):
        super().__init__("not_found", 404)
        self.order_number = order_number


class EvidenceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = EvidenceRepository(db)
        self.orders = OrderService(db)

    def _require_registered_order(
        self, number: str | None, *, measure_id: str,
        actor_user_id: int, action: str,
    ) -> None:
        """Відхилити неіснуючий наказ, але зберегти ОКРЕМИЙ запис аудиту.

        Evidence при цьому не створюється/не змінюється. Подію читає RF8.
        Для порожнього номера нічого не записуємо (not_provided дозволений).
        """
        if self.orders.verify_number(number) != "not_found":
            return
        cleaned = number.strip()
        self.db.add(InvalidOrderReference(
            id=str(uuid4()), measure_id=measure_id,
            actor_user_id=actor_user_id,
            order_number=cleaned, action=action,
        ))
        # Комітимо ТІЛЬКИ журнал відмови, перед HTTP 404.
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        raise OrderReferenceNotFound(cleaned)

    def as_read(self, evidence: Evidence) -> EvidenceRead:
        """Статус перевіряється ЗАРАЗ, не фіксується назавжди у таблиці."""
        data = EvidenceRead.model_validate(evidence)
        return data.model_copy(update={
            "order_check_status": self.orders.verify_number(evidence.order_number)
        })

    def get_evidence(self, evidence_id: str) -> Evidence:
        evidence = self.repo.get_by_id(evidence_id)
        if evidence is None:
            raise EvidenceError("Документ не знайдено", 404)
        return evidence

    def list_evidences(
        self, skip: int = 0, limit: int = 20, measure_id: str | None = None
    ) -> list[Evidence]:
        return self.repo.list_evidences(skip, limit, measure_id)

    def check_measure(self, measure_id: str) -> None:
        if self.db.get(Measure, measure_id) is None:
            raise EvidenceError("Захід із таким ID не існує", 422)

    def create_evidence(self, data: EvidenceCreate, *, actor_user_id: int) -> Evidence:
        if self.repo.get_by_id(data.id) is not None:
            raise EvidenceError("Документ із таким ID вже існує", 409)
        self.check_measure(data.measure_id)
        # Перевірка до створення об'єкта та ДО db.commit().
        self._require_registered_order(
            data.order_number, measure_id=data.measure_id,
            actor_user_id=actor_user_id, action="create",
        )
        uploaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
        evidence = Evidence(**data.model_dump(), uploaded_at=uploaded_at)
        try:
            return self.repo.save(evidence)
        except IntegrityError as exc:
            self.db.rollback()
            raise EvidenceError("Не вдалося створити документ", 409) from exc

    def update_evidence(
        self, evidence_id: str, data: EvidenceUpdate, *, actor_user_id: int
    ) -> Evidence:
        evidence = self.get_evidence(evidence_id)
        changes = data.model_dump(exclude_unset=True)
        required_fields = {"measure_id", "document_type", "title", "reference_sha256"}
        for key, value in changes.items():
            if key in required_fields and value is None:
                raise EvidenceError(f"Поле {key} не може бути null")
        if "measure_id" in changes:
            self.check_measure(changes["measure_id"])
        # Валідовуємо кінцеве значення номера до змін ORM-об'єкта.
        self._require_registered_order(
            changes.get("order_number", evidence.order_number),
            measure_id=changes.get("measure_id") or evidence.measure_id,
            actor_user_id=actor_user_id, action="update",
        )
        for key, value in changes.items():
            setattr(evidence, key, value)
        try:
            return self.repo.save(evidence)
        except IntegrityError as exc:
            self.db.rollback()
            raise EvidenceError("Не вдалося оновити документ", 409) from exc

    def delete_evidence(self, evidence_id: str) -> None:
        evidence = self.get_evidence(evidence_id)
        try:
            self.repo.delete(evidence)
        except IntegrityError as exc:
            self.db.rollback()
            raise EvidenceError("Документ має пов'язані записи", 409) from exc
