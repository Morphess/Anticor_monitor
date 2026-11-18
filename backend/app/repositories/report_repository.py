from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report import Report


class ReportRepository:

    def __init__(self, db: Session):
        self.db = db

    # Отримати звіт за ID
    def get_by_id(self, report_id: int) -> Report | None:

        return self.db.get(Report, report_id)

    # Отримати список звітів
    def list_reports(
        self,
        skip: int = 0,
        limit: int = 20,
        program_id: str | None = None,
        period: str | None = None,
        status: str | None = None,
    ) -> list[Report]:

        stmt = select(Report)

        if program_id is not None:
            stmt = stmt.where(Report.program_id == program_id)

        if period is not None:
            stmt = stmt.where(Report.period == period)

        if status is not None:
            stmt = stmt.where(Report.status == status)

        stmt = (
            stmt.order_by(Report.generated_at.desc(), Report.id.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(self.db.scalars(stmt).all())

    # Перевірка існування версії
    def version_exists(self, program_id: str, period: str, version: int) -> bool:

        stmt = select(Report.id).where(
            Report.program_id == program_id,
            Report.period == period,
            Report.version == version,
        )

        return self.db.scalar(stmt.limit(1)) is not None

    # Створення або оновлення
    def save(self, report: Report) -> Report:

        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        return report

    # Видалення звіту
    def delete(self, report: Report) -> None:

        self.db.delete(report)
        self.db.commit()
