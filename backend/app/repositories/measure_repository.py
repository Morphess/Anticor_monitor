from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.measure import Measure


class MeasureRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати захід за ID
    def get_by_id(self, measure_id: str) -> Measure | None:

        return self.db.get(Measure, measure_id)

    # Отримати список заходів
    def list_measures(
        self,
        skip: int = 0,
        limit: int = 20,
        program_id: str | None = None,
        section_id: str | None = None,
    ) -> list[Measure]:

        stmt = select(Measure)

        # Фільтр за програмою
        if program_id is not None:
            stmt = stmt.where(Measure.program_id == program_id)

        # Фільтр за розділом
        if section_id is not None:
            stmt = stmt.where(Measure.section_id == section_id)

        stmt = (
            stmt.order_by(
                Measure.program_id, Measure.section_id, Measure.sequence_number
            )
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())

    # Перевірка унікальності номера заходу
    def number_taken(
        self,
        program_id: str,
        section_id: str,
        sequence_number: int,
        exclude_id: str | None = None,
    ) -> bool:

        stmt = select(Measure.id).where(
            Measure.program_id == program_id,
            Measure.section_id == section_id,
            Measure.sequence_number == sequence_number,
        )

        # Під час редагування не враховуємо сам захід
        if exclude_id is not None:
            stmt = stmt.where(Measure.id != exclude_id)

        return self.db.scalar(stmt.limit(1)) is not None

    # Створення або збереження змін
    def save(self, measure: Measure) -> Measure:

        self.db.add(measure)
        self.db.commit()
        self.db.refresh(measure)

        return measure

    # Видалення заходу
    def delete(self, measure: Measure) -> None:

        self.db.delete(measure)
        self.db.commit()
