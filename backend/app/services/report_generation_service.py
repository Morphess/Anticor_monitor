"""Формування піврічного звіту НА ОСНОВІ даних заходів та виконань.

Report зберігає лише метадані, а JSON-снепшот — вміст конкретної версії.
Після генерації рядки не обчислюються повторно при завантаженні CSV/HTML.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.report import Report
from app.models.measure import Measure, MeasureCollaborator
from app.models.program_workflow import MeasureAssignment
from app.models.user import User
from app.repositories.report_data_repository import ReportDataRepository
from app.schemas.report_portal import (
    PortalHalfYearReport,
    ReportMeasureRow,
    ReportSectionBlock,
    ReportSummary,
)
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError
from app.services.report_services import ReportError


STATUSES = {
    "completed": "Виконано",
    "vykonano": "Виконано",
    "partial": "Частково виконано",
    "chastkovo": "Частково виконано",
}
NOT_COMPLETED = "Не виконано"
NOT_DUE = "Строк виконання заходу не настав"


def half_year_bounds(period: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-H[12]", period):
        raise ReportError("Період має формат YYYY-H1 або YYYY-H2", 422)
    year, half = int(period[:4]), period[-1]
    if half == "1":
        return date(year, 1, 1), date(year, 6, 30)
    return date(year, 7, 1), date(year, 12, 31)


def export_root() -> Path:
    # Каталог поза backend/app. У Docker слід примонтувати як persistent volume.
    default_path = Path(__file__).resolve().parents[2] / "generated_reports"
    root = Path(os.getenv("REPORT_EXPORT_DIR", str(default_path))).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validated_snapshot_path(path_text: str | None) -> Path:
    if not path_text:
        raise ReportError("Звіт ще не сформовано", 409)
    root = export_root()
    path = Path(path_text).resolve()
    # Забороняємо довільні шляхи із таблиці reports.
    if path.parent != root or path.suffix != ".json":
        raise ReportError("Недопустимий шлях експорту звіту", 409)
    return path


class ReportGenerationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReportDataRepository(db)

    def build(self, program_id: str, period: str, actor) -> PortalHalfYearReport:
        start, end = half_year_bounds(period)
        today = date.today()
        if start > today:
            raise ReportError("Звітний період ще не почався", 422)
        as_of = min(today, end)
        program = self.repo.program(program_id)
        if program is None:
            raise ReportError("Програму не знайдено", 404)

        if actor.role_id not in ("MAIN_KOORD", "KOORD"):
            raise ReportError("Недостатньо прав на формування звіту", 403)

        try:
            workflow = ProgramWorkflowService(self.db)
            visible = workflow.program_measures(program_id, actor)
            ids = {row["id"] for row in visible}
            scoped_users = None
            scope_departments = None
            if actor.role_id == "KOORD":
                if not actor.department_id or not workflow.tree.exists(actor.department_id):
                    raise ReportError("Координатору не призначено коректний підрозділ", 403)
                scope_departments = workflow.tree.descendants(actor.department_id)
                # Directly dispatched program, but only the coordinator's subtree
                # belongs in the generated snapshot. An assigned executor's
                # department is the source of truth for delegated measures.
                assigned = self.db.execute(
                    select(MeasureAssignment.measure_id, MeasureAssignment.user_id)
                    .join(User, User.id == MeasureAssignment.user_id)
                    .where(MeasureAssignment.measure_id.in_(ids),
                           MeasureAssignment.department_id.in_(scope_departments),
                           User.department_id == MeasureAssignment.department_id,
                           User.role_id == "VYK")
                ).all() if ids else []
                scoped_users = {}
                for mid, uid in assigned:
                    scoped_users.setdefault(mid, set()).add(uid)
                # A measure can be the responsibility of this department even
                # before any executor is assigned. Do not include foreign units.
                in_branch = set(self.db.scalars(
                    select(Measure.id)
                    .outerjoin(MeasureCollaborator, MeasureCollaborator.measure_id == Measure.id)
                    .where(Measure.id.in_(ids), or_(
                        Measure.responsible_department_id.in_(scope_departments),
                        MeasureCollaborator.department_id.in_(scope_departments),
                    )).distinct()
                )) if ids else set()
                ids = (in_branch | set(scoped_users)) & ids
        except WorkflowError as exc:
            raise ReportError(exc.detail, exc.status_code) from exc

        measures = self.repo.measures(ids)
        executions = self.repo.executions(ids, period, allowed_users=scoped_users)
        evidence_counts = self.repo.evidence_counts(ids, period, allowed_users=scoped_users)
        dep_names = self.repo.departments({m.responsible_department_id for m in measures if m.responsible_department_id})

        # У звіті Порталу доброчесності рівно три розділи.
        source_sections = self.repo.sections()
        by_number = {section.number: section for section in source_sections}
        if not all(number in by_number for number in (1, 2, 3)):
            raise ReportError("Для звіту потрібні розділи №1, №2 і №3", 409)
        sections = [
            ReportSectionBlock(
                section_id=by_number[number].id,
                number=number,
                title=by_number[number].title,
            )
            for number in (1, 2, 3)
        ]
        section_map = {s.section_id: s for s in sections}
        for measure in sorted(measures, key=lambda m: (section_map[m.section_id].number if m.section_id in section_map else 9999, m.sequence_number or 0, m.id)):
            if measure.section_id not in section_map:
                # Не губимо захід, якщо довідник пошкоджено: це помилка даних.
                raise ReportError(f"Для заходу {measure.id} немає розділу {measure.section_id}", 409)
            execution = executions.get(measure.id)
            # `status` is coordinator review state, not the old outcome status.
            # A submitted or rejected claim must NOT count as completed.
            approved = bool(
                execution and execution.status == "approved"
                and not execution.document_changed
            )
            raw_status = (
                (execution.outcome_status or "completed").lower()
                if approved else ""
            )
            is_not_due = (
                measure.deadline_type == "date"
                and measure.deadline_on is not None
                and measure.deadline_on > as_of
                and raw_status not in STATUSES
            )
            status = NOT_DUE if is_not_due else STATUSES.get(raw_status, NOT_COMPLETED)
            description = (execution.result_description or "").strip() if execution else ""
            if status == NOT_DUE:
                description = ""  # Поле за специфікацією лишається порожнім.

            if measure.deadline_type in ("ongoing", "recurring"):
                # Для завершеного півріччя — 30 червня / 31 грудня.
                # У поточному періоді відображаємо тільки дату зрізу.
                factual_date = as_of
            else:
                factual_date = execution.completed_on if execution else None

            warnings = []
            if execution is not None and not approved:
                warnings.append("Виконання ще не погоджено координатором")
                if execution.status == "rejected":
                    reason = (execution.rejection_reason or "").strip()
                    warnings.append("Виконання відхилено координатором" +
                                    (f": {reason}" if reason else ""))
                if execution.document_changed:
                    warnings.append("Документ змінено — потрібне повторне подання")
            if status == NOT_COMPLETED and not description:
                warnings.append("Не зазначено пояснення причин невиконання")
            if status == "Виконано" and factual_date is None:
                warnings.append("Не зазначено фактичну дату виконання")
            if status in ("Виконано", "Частково виконано") and evidence_counts.get(measure.id, 0) == 0:
                warnings.append("Відсутні підтвердні матеріали")

            row = ReportMeasureRow(
                measure_id=measure.id,
                sequence_number=measure.sequence_number,
                measure_description=measure.description,
                responsible_department_id=(measure.responsible_department_id
                    if scope_departments is None or measure.responsible_department_id in scope_departments
                    else None),
                responsible_department=(dep_names.get(measure.responsible_department_id)
                    if scope_departments is None or measure.responsible_department_id in scope_departments
                    else None),
                risk_id=measure.risk_id,
                factual_date=factual_date,
                execution_status=status,
                result_description=description,
                indicator_actual=execution.indicator_actual if execution else None,
                indicator_target=measure.indicator_target,
                approved_by_coordinator=approved,
                evidence_count=evidence_counts.get(measure.id, 0),
                warnings=warnings,
            )
            section_map[measure.section_id].measures.append(row)

        rows = [m for block in sections for m in block.measures]
        summary = ReportSummary(
            total=len(rows),
            completed=sum(r.execution_status == "Виконано" for r in rows),
            partial=sum(r.execution_status == "Частково виконано" for r in rows),
            not_completed=sum(r.execution_status == NOT_COMPLETED for r in rows),
            not_due=sum(r.execution_status == NOT_DUE for r in rows),
            unapproved=sum("Виконання ще не погоджено координатором" in r.warnings for r in rows),
            missing_explanations=sum("Не зазначено пояснення причин невиконання" in r.warnings for r in rows),
        )
        return PortalHalfYearReport(
            program_id=program_id,
            program_title=program.title,
            period=period,
            period_start=start,
            period_end=end,
            as_of=as_of,
            is_preliminary=as_of < end,
            generated_at=datetime.now(timezone.utc),
            scope="program" if actor.role_id == "MAIN_KOORD" else "department",
            department_id=None if actor.role_id == "MAIN_KOORD" else actor.department_id,
            sections=sections,
            summary=summary,
        )

    def _save_snapshot(self, report: Report, actor) -> Report:
        if report.status != "draft":
            raise ReportError("Формувати можна тільки чернетку", 409)
        snapshot = self.build(report.program_id, report.period, actor)
        path = export_root() / f"report-{report.id}-{uuid.uuid4().hex}.json"
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("x", encoding="utf-8") as stream:
                # Mark newly restricted KOORD snapshots. Older files may include
                # all program measures and must not be exposed as subtree reports.
                document = snapshot.model_dump(mode="json")
                if actor.role_id == "KOORD":
                    document["_koord_subtree_scope_v1"] = actor.department_id
                stream.write(json.dumps(document, ensure_ascii=False, indent=2))
            tmp.replace(path)
            report.status = "generated"
            report.generated_at = snapshot.generated_at
            report.export_file_path = str(path)
            self.db.commit()
            self.db.refresh(report)
            return report
        except Exception:
            self.db.rollback()
            tmp.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            raise

    def generate_draft(self, report: Report, actor) -> Report:
        if actor.role_id == "KOORD" and report.generated_by_user_id != actor.id:
            raise ReportError("KOORD може формувати лише власні чернетки", 403)
        return self._save_snapshot(report, actor)

    def auto_generate(self, program_id: str, period: str, actor) -> Report:
        half_year_bounds(period)
        if self.repo.program(program_id) is None:
            raise ReportError("Програму не знайдено", 404)
        latest_version = self.db.scalar(
            select(func.coalesce(func.max(Report.version), 0)).where(
                Report.program_id == program_id, Report.period == period
            )
        )
        report = Report(
            program_id=program_id,
            period=period,
            version=int(latest_version or 0) + 1,
            status="draft",
            generated_by_user_id=actor.id,
        )
        self.db.add(report)
        try:
            self.db.flush()  # Отримуємо ID без окремого commit.
            return self._save_snapshot(report, actor)
        except IntegrityError as exc:
            self.db.rollback()
            raise ReportError("Конфлікт номера версії звіту; спробуй ще раз", 409) from exc
        except Exception:
            self.db.rollback()
            raise

    def read_snapshot(self, report: Report) -> PortalHalfYearReport:
        path = _validated_snapshot_path(report.export_file_path)
        if report.status not in ("generated", "submitted"):
            raise ReportError("Звіт ще не сформовано", 409)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            author = self.db.get(User, report.generated_by_user_id) if report.generated_by_user_id else None
            if author is not None and author.role_id == "KOORD":
                if (not isinstance(raw, dict) or
                        raw.get("_koord_subtree_scope_v1") != author.department_id):
                    raise ReportError(
                        "Стару версію звіту створено до обмеження підрозділів. "
                        "Задля конфіденційності сформуйте нову версію.", 409
                    )
            return PortalHalfYearReport.model_validate(raw)
        except FileNotFoundError as exc:
            raise ReportError("Файл версії звіту відсутній на сервері", 404) from exc
        except ValueError as exc:
            raise ReportError("Файл версії звіту пошкоджено", 409) from exc


def _safe_csv(value: object) -> str:
    """Захист Excel/LibreOffice від інтерпретації даних як формул."""
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_export(report: PortalHalfYearReport) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([
        "Розділ", "№ заходу", "ID заходу", "Зміст заходу",
        "Відповідальний підрозділ", "Фактичний строк виконання",
        "Стан виконання", "Опис результату виконання заходу або пояснення причин невиконання",
        "Корупційний ризик", "Індикатор (факт)", "Індикатор (ціль)",
        "Погоджено", "Кількість підтвердних матеріалів",
    ])
    for section in report.sections:
        for row in section.measures:
            writer.writerow([_safe_csv(val) for val in (
                section.title,
                row.sequence_number,
                row.measure_id,
                row.measure_description,
                row.responsible_department or row.responsible_department_id,
                row.factual_date.isoformat() if row.factual_date else "",
                row.execution_status,
                row.result_description,
                row.risk_id,
                row.indicator_actual,
                row.indicator_target,
                "Так" if row.approved_by_coordinator else "Ні",
                row.evidence_count,
            )])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def print_html(report: PortalHalfYearReport) -> str:
    esc = lambda val: html.escape("" if val is None else str(val), quote=True)
    scope = "Повна програма" if report.scope == "program" else f"Витяг підрозділу {esc(report.department_id)}"
    preliminary = "Попередній стан, не підсумковий звіт" if report.is_preliminary else "Завершений звітний період"
    sections_markup = []
    for section in report.sections:
        data_rows = "".join(
            "<tr>"
            f"<td>{esc(row.sequence_number)}</td>"
            f"<td>{esc(row.measure_description)}</td>"
            f"<td>{esc(row.factual_date.isoformat() if row.factual_date else '')}</td>"
            f"<td>{esc(row.execution_status)}</td>"
            f"<td>{esc(row.result_description)}</td>"
            "</tr>"
            for row in section.measures
        ) or '<tr><td colspan="5">Заходів немає</td></tr>'
        sections_markup.append(
            f"<h2>{esc(section.number)}. {esc(section.title)}</h2>"
            "<table><thead><tr><th>№</th><th>Захід</th>"
            "<th>Фактичний строк</th><th>Стан виконання</th>"
            "<th>Результат або пояснення</th></tr></thead><tbody>"
            f"{data_rows}</tbody></table>"
        )
    return ("<!DOCTYPE html><html lang='uk'><head><meta charset='utf-8'>"
            "<title>Звіт антикорупційної програми</title>"
            "<style>@page{size:A4 landscape;margin:12mm}"
            "body{font-family:Arial,sans-serif;font-size:11px;color:#111}"
            "table{width:100%;border-collapse:collapse;table-layout:fixed;margin:12px 0 22px}"
            "th,td{border:1px solid #888;padding:6px;word-wrap:break-word;vertical-align:top}"
            "thead{display:table-header-group}tr{break-inside:avoid}"
            "h1{font-size:20px}h2{font-size:15px;margin-top:28px}"
            "small{color:#555}</style></head><body>"
            f"<h1>Звіт про виконання антикорупційної програми</h1>"
            f"<p><strong>{esc(report.program_title)}</strong> — {esc(report.period)}</p>"
            f"<p><small>{scope} · {preliminary} · Дані станом на {esc(report.as_of)}"
            " · Для друку: Ctrl+P → Зберегти як PDF</small></p>"
            + "".join(sections_markup)
            + "</body></html>")
