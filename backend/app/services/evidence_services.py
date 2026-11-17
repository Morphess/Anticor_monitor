from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.measure import Measure

from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidences import EvidenceCreate, EvidenceUpdate


# Помилка бізнес-логіки
class EvidenceError(Exception):

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class EvidenceService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = EvidenceRepository(db)

    # READ — отримати документ за ID
    def get_evidence(self, evidence_id: str) -> Evidence:

        evidence = self.repo.get_by_id(evidence_id)

        if evidence is None:
            raise EvidenceError("Документ не знайдено", 404)

        return evidence

    # READ — отримати список документів
    def list_evidences(
        self, skip: int = 0, limit: int = 20, measure_id: str | None = None
    ) -> list[Evidence]:

        return self.repo.list_evidences(skip, limit, measure_id)

    # Перевірити існування заходу
    def check_measure(self, measure_id: str) -> None:

        measure = self.db.get(Measure, measure_id)

        if measure is None:
            raise EvidenceError("Захід із таким ID не існує", 422)

    # CREATE — створити документ
    def create_evidence(self, data: EvidenceCreate) -> Evidence:

        # Перевіряємо унікальність ID
        if self.repo.get_by_id(data.id) is not None:
            raise EvidenceError("Документ із таким ID вже існує", 409)

        # Перевіряємо захід
        self.check_measure(data.measure_id)

        # Час додавання встановлює сервер
        # Зберігаємо UTC без timezone,
        # оскільки модель має timezone=False
        uploaded_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Створюємо документ
        evidence = Evidence(**data.model_dump(), uploaded_at=uploaded_at)

        try:
            return self.repo.save(evidence)

        except IntegrityError as error:
            self.db.rollback()

            raise EvidenceError("Не вдалося створити документ", 409) from error

    # UPDATE — редагувати документ
    def update_evidence(self, evidence_id: str, data: EvidenceUpdate) -> Evidence:

        evidence = self.get_evidence(evidence_id)

        # Беремо тільки передані поля
        changes = data.model_dump(exclude_unset=True)

        # Ці поля не можуть бути NULL
        required_fields = {"measure_id", "document_type", "title", "reference_sha256"}

        for field, value in changes.items():
            if field in required_fields and value is None:
                raise EvidenceError(f"Поле {field} не може бути null")

        # Якщо змінюємо захід — перевіряємо його
        if "measure_id" in changes:
            self.check_measure(changes["measure_id"])

        # Оновлюємо лише передані поля
        for field, value in changes.items():
            setattr(evidence, field, value)

        try:
            return self.repo.save(evidence)

        except IntegrityError as error:
            self.db.rollback()

            raise EvidenceError("Не вдалося оновити документ", 409) from error

    # DELETE — видалити документ
    def delete_evidence(self, evidence_id: str) -> None:

        evidence = self.get_evidence(evidence_id)

        try:
            self.repo.delete(evidence)

        except IntegrityError as error:
            self.db.rollback()

            raise EvidenceError("Документ має пов'язані записи", 409) from error
