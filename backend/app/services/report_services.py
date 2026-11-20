"""CRUD карток звітів. Генерація в ReportGenerationService.

Стадію generated дозволено встановлювати лише через реальне створення
незмінного JSON-снепшоту, а не простим PATCH статусу.
"""
from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.program import Program
from app.models.report import Report
from app.repositories.report_repository import ReportRepository
from app.schemas.reports import ReportCreate, ReportUpdate


class ReportError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReportRepository(db)

    def get_report(self, report_id: int) -> Report:
        report = self.repo.get_by_id(report_id)
        if report is None:
            raise ReportError("Звіт не знайдено", 404)
        return report

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

    def check_program(self, program_id: str) -> None:
        if self.db.get(Program, program_id) is None:
            raise ReportError("Антикорупційна програма не існує", 422)

    def create_report(self, data: ReportCreate, user_id: int) -> Report:
        self.check_program(data.program_id)
        if not re.fullmatch(r"\d{4}-H[12]", data.period):
            raise ReportError("Період має формат YYYY-H1 або YYYY-H2", 422)
        if self.repo.version_exists(data.program_id, data.period, data.version):
            raise ReportError("Звіт із такою версією вже існує для програми та періоду", 409)
        # Тільки сервер визначає статус і автора.
        fields = data.model_dump(exclude={"status", "generated_by_user_id", "export_file_path", "generated_at"})
        report = Report(**fields, status="draft", generated_by_user_id=user_id)
        try:
            return self.repo.save(report)
        except IntegrityError as exc:
            self.db.rollback()
            raise ReportError("Не вдалося створити звіт: конфлікт даних", 409) from exc

    def update_report(self, report_id: int, data: ReportUpdate) -> Report:
        report = self.get_report(report_id)
        if report.status == "submitted":
            raise ReportError("Поданий звіт не можна редагувати", 409)

        changes = data.model_dump(exclude_unset=True)
        forbidden = {"program_id", "period", "version", "generated_by_user_id", "export_file_path", "generated_at"}
        if forbidden & changes.keys():
            raise ReportError("Метадані, версію та шлях експорту змінювати заборонено", 422)
        if set(changes) - {"status"}:
            raise ReportError("Оновлювати можна тільки статус звіту", 422)
        if not changes or changes.get("status") == report.status:
            return report
        new_status = changes.get("status")
        if new_status is None:
            raise ReportError("Статус не може бути null", 422)
        if report.status == "draft":
            raise ReportError("Для формування використовуй POST /reports/{id}/generate", 409)
        if not (report.status == "generated" and new_status == "submitted"):
            raise ReportError("Недопустимий перехід статусу", 409)

        # Перевірка: подається саме збережена версія, а не лише позначка status.
        from app.services.report_generation_service import ReportGenerationService
        snapshot = ReportGenerationService(self.db).read_snapshot(report)
        if snapshot.is_preliminary:
            raise ReportError("Підсумковий звіт можна подати тільки після завершення півріччя", 409)
        if snapshot.summary.unapproved:
            raise ReportError("Є непогоджені виконання; сформуй нову версію після погодження", 409)
        if snapshot.summary.missing_explanations:
            raise ReportError("Відсутні пояснення невиконання; сформуй нову версію після виправлення", 409)
        report.status = "submitted"
        try:
            return self.repo.save(report)
        except IntegrityError as exc:
            self.db.rollback()
            raise ReportError("Не вдалося подати звіт", 409) from exc

    def delete_report(self, report_id: int) -> None:
        report = self.get_report(report_id)
        if report.status != "draft":
            raise ReportError("Можна видаляти лише чернетки звітів", 409)
        try:
            self.repo.delete(report)
        except IntegrityError as exc:
            self.db.rollback()
            raise ReportError("Не вдалося видалити звіт", 409) from exc
