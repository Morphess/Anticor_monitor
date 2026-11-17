from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence


class EvidenceRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати документ за ID
    def get_by_id(self, evidence_id: str) -> Evidence | None:

        return self.db.get(Evidence, evidence_id)

    # Отримати список документів
    def list_evidences(
        self, skip: int = 0, limit: int = 20, measure_id: str | None = None
    ) -> list[Evidence]:

        stmt = select(Evidence)

        # Фільтрація за заходом
        if measure_id is not None:
            stmt = stmt.where(Evidence.measure_id == measure_id)

        stmt = (
            stmt.order_by(Evidence.uploaded_at.desc(), Evidence.id)
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())

    # Створення або оновлення документа
    def save(self, evidence: Evidence) -> Evidence:

        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)

        return evidence

    # Видалення документа
    def delete(self, evidence: Evidence) -> None:

        self.db.delete(evidence)
        self.db.commit()
