from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.program import Program
from app.models.report import Report

from app.repositories.report_repository import ReportRepository
from app.schemas.reports import ReportCreate, ReportUpdate


# Помилка бізнес-логіки
class ReportError(Exception):

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class ReportService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = ReportRepository(db)

    # READ — отримати один звіт
    def get_report(self, report_id: int) -> Report:

        report = self.repo.get_by_id(report_id)

        if report is None:
            raise ReportError("Звіт не знайдено", 404)

        return report

    # READ — отримати список звітів
    def list_reports(
        self,
        skip: int = 0,
        limit: int = 20,
        program_id: str | None = None,
        period: str | None = None,
        status: str | None = None,
    ) -> list[Report]:

        return self.repo.list_reports(
            skip=skip, limit=limit, program_id=program_id, period=period, status=status
        )

    # Перевірка існування програми
    def check_program(self, program_id: str) -> None:

        program = self.db.get(Program, program_id)

        if program is None:
            raise ReportError("Антикорупційна програма не існує", 422)

    # CREATE — створити звіт
    def create_report(self, data: ReportCreate, user_id: int) -> Report:

        # Перевіряємо програму
        self.check_program(data.program_id)

        # Перевіряємо унікальність версії
        if self.repo.version_exists(data.program_id, data.period, data.version):
            raise ReportError(
                "Звіт із такою версією вже існує " "для цієї програми та періоду", 409
            )

        # Створюємо запис про звіт
        report = Report(
            **data.model_dump(), status="draft", generated_by_user_id=user_id
        )

        # generated_at встановлюється PostgreSQL
        try:
            return self.repo.save(report)

        except IntegrityError as error:
            self.db.rollback()

            raise ReportError(
                "Не вдалося створити звіт: конфлікт даних", 409
            ) from error

    # UPDATE — редагувати звіт
    def update_report(self, report_id: int, data: ReportUpdate) -> Report:

        report = self.get_report(report_id)

        # Подані звіти не редагуємо
        if report.status == "submitted":
            raise ReportError("Поданий звіт не можна редагувати", 409)

        # Беремо лише передані поля
        changes = data.model_dump(exclude_unset=True)

        if "status" in changes:

            new_status = changes["status"]

            if new_status is None:
                raise ReportError("Статус не може бути null")

            # Дозволені переходи між статусами
            allowed_transitions = {"draft": "generated", "generated": "submitted"}

            # Якщо статус змінюється
            if new_status != report.status:

                expected_status = allowed_transitions.get(report.status)

                if new_status != expected_status:
                    raise ReportError("Недопустима зміна статусу звіту", 409)

        # Оновлюємо лише передані поля
        for field, value in changes.items():
            setattr(report, field, value)

        try:
            return self.repo.save(report)

        except IntegrityError as error:
            self.db.rollback()

            raise ReportError("Не вдалося оновити звіт", 409) from error

    # DELETE — видалити звіт
    def delete_report(self, report_id: int) -> None:

        report = self.get_report(report_id)

        # Видаляти дозволено лише чернетки
        if report.status != "draft":
            raise ReportError("Можна видаляти лише чернетки звітів", 409)

        try:
            self.repo.delete(report)

        except IntegrityError as error:
            self.db.rollback()

            raise ReportError("Не вдалося видалити звіт", 409) from error
