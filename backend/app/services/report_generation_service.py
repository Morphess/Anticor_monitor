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
from app.models.risk import Risk
from app.models.user import User
from app.repositories.report_data_repository import ReportDataRepository
from app.schemas.report_portal import (
    PortalHalfYearReport,
    ReportMeasureRow,
    ReportMeasureOverride,
    ReportRisk,
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


def period_label(period: str) -> str:
    """«2026-H1» → «Звіт за перше півріччя 2026 року» (формулювання Порталу НАЗК)."""
    half = "перше" if period.endswith("H1") else "друге"
    return f"Звіт за {half} півріччя {period[:4]} року"


def planned_deadline(measure) -> str:
    """«Запланований строк виконання заходу» у формі, як у звіті НАЗК."""
    if measure.deadline_type == "date" and measure.deadline_on is not None:
        text = measure.deadline_on.strftime("%d.%m.%Y")
        desc = (measure.deadline_description or "").strip()
        if not desc or desc in (text, measure.deadline_on.isoformat()):
            return text
        return desc if text in desc else f"{desc} ({text})"
    if measure.deadline_type == "ongoing":
        return (measure.deadline_description or "").strip() or "Постійно"
    return (measure.deadline_description or "").strip() or "Періодично"


def half_year_bounds(period: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-H[12]", period):
        raise ReportError("Період має формат YYYY-H1 або YYYY-H2", 422)
    year, half = int(period[:4]), period[-1]
    if half == "1":
        return date(year, 1, 1), date(year, 6, 30)
    return date(year, 7, 1), date(year, 12, 31)


def export_root() -> Path:
    # Каталог поза backend/app. У Docker слід примонтувати як persistent volume.
    default_path = Path(__file__).resolve().parents[3] / "reports"
    root = Path(os.getenv("REPORT_EXPORT_DIR", str(default_path))).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
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

    def build(self, program_id: str, period: str, actor,
              overrides: list[ReportMeasureOverride] | None = None) -> PortalHalfYearReport:
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

        notes: dict[str, ReportMeasureOverride] = {}
        for entry in overrides or []:
            if entry.measure_id in notes:
                raise ReportError(f"Повторний запис заходу: {entry.measure_id}", 422)
            if entry.measure_id not in ids:
                raise ReportError("Не можна редагувати захід поза доступним звітом", 403)
            notes[entry.measure_id] = entry

        measures = self.repo.measures(ids)
        executions = self.repo.executions(ids, period, allowed_users=scoped_users)
        evidence_counts = self.repo.evidence_counts(ids, period, allowed_users=scoped_users)

        # Відповідальний підрозділ для НАЗК — це підрозділ, який реально виконує
        # захід (підрозділи призначених виконавців). measure.responsible_department_id
        # заповнюється підрозділом автора заходу, тож лишається лише запасним варіантом.
        assigned_departments: dict[str, set[str]] = {}
        if ids:
            assignment_query = (select(MeasureAssignment.measure_id, MeasureAssignment.department_id)
                .join(User, User.id == MeasureAssignment.user_id)
                .where(MeasureAssignment.measure_id.in_(ids),
                       User.role_id == "VYK",
                       User.department_id == MeasureAssignment.department_id))
            if scope_departments is not None:
                assignment_query = assignment_query.where(
                    MeasureAssignment.department_id.in_(scope_departments))
            for mid, dep_id in self.db.execute(assignment_query):
                if dep_id:
                    assigned_departments.setdefault(mid, set()).add(dep_id)
        dep_names = self.repo.departments(
            {m.responsible_department_id for m in measures if m.responsible_department_id}
            | {d for deps in assigned_departments.values() for d in deps}
        )
        risk_ids = {m.risk_id for m in measures if m.risk_id}
        risks = ({r.id: r for r in self.db.scalars(select(Risk).where(Risk.id.in_(risk_ids)))}
                 if risk_ids else {})

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
                # Дату зрізу можна вважати фактичною лише за погодженого результату.
                factual_date = as_of if approved else None
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
            # Only the coordinator authors actual outcomes in a report version.
            # A claim without approved orders can NEVER be promoted to completed.
            note = notes.get(measure.id)
            if note is not None:
                if note.execution_status is not None:
                    if not approved and note.execution_status != NOT_COMPLETED:
                        raise ReportError(
                            f"Захід {measure.id}: немає всіх погоджених виконань", 409
                        )
                    if status == NOT_DUE:
                        raise ReportError(f"Захід {measure.id}: строк ще не настав", 409)
                    status = note.execution_status
                if note.result_description is not None:
                    description = note.result_description.strip()
                if note.factual_date is not None:
                    if note.factual_date > as_of:
                        raise ReportError(
                            f"Захід {measure.id}: фактична дата після дати зрізу", 422
                        )
                    if not approved:
                        raise ReportError(
                            f"Захід {measure.id}: дату виконання можна зазначити лише після погодження", 409
                        )
                    factual_date = note.factual_date
            if status == NOT_COMPLETED and not description:
                warnings.append("Не зазначено пояснення причин невиконання")
            if status in ("Виконано", "Частково виконано") and not description:
                warnings.append("Не зазначено опис результату виконання")
            if status in ("Виконано", "Частково виконано") and factual_date is None:
                warnings.append("Не зазначено фактичну дату виконання")
            if status in ("Виконано", "Частково виконано") and evidence_counts.get(measure.id, 0) == 0:
                warnings.append("Відсутні підтвердні матеріали")

            executing = sorted(assigned_departments.get(measure.id, set()))
            if executing:
                responsible_id = executing[0] if len(executing) == 1 else ", ".join(executing)
                responsible_name = "; ".join(dep_names.get(d, d) for d in executing)
            elif scope_departments is None or measure.responsible_department_id in scope_departments:
                responsible_id = measure.responsible_department_id
                responsible_name = dep_names.get(measure.responsible_department_id)
            else:
                responsible_id = responsible_name = None
            if not executing:
                warnings.append("Захід не призначено жодному виконавцю")

            section_number = section_map[measure.section_id].number
            participants = None
            if section_number == 3 and execution is not None and execution.indicator_actual is not None:
                participants = int(execution.indicator_actual)
            if note is not None and note.participants_count is not None:
                if section_number != 3:
                    raise ReportError("Кількість учасників передбачена лише для розділу 3", 422)
                participants = note.participants_count
            indicator_actual = execution.indicator_actual if execution else None
            if note is not None and note.indicator_actual is not None:
                indicator_actual = note.indicator_actual
            risk = risks.get(measure.risk_id) if measure.risk_id else None

            row = ReportMeasureRow(
                measure_id=measure.id,
                sequence_number=measure.sequence_number,
                measure_description=measure.description,
                responsible_department_id=responsible_id,
                responsible_department=responsible_name,
                planned_deadline=planned_deadline(measure),
                completion_indicator=measure.completion_indicator,
                indicator_unit=measure.indicator_unit,
                participants_count=participants,
                risk=ReportRisk(
                    risk_id=risk.id, sphere=risk.process_name, title=risk.title,
                    description=risk.description, level=risk.level,
                ) if risk is not None else None,
                risk_id=measure.risk_id,
                factual_date=factual_date,
                execution_status=status,
                result_description=description,
                indicator_actual=indicator_actual,
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
            missing_results=sum(
                any(w in r.warnings for w in
                    ("Не зазначено опис результату виконання",
                     "Не зазначено фактичну дату виконання"))
                for r in rows
            ),
        )
        return PortalHalfYearReport(
            program_id=program_id,
            program_title=program.title,
            organization_name=program.organization_name,
            period_label=period_label(period),
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

    def _save_snapshot(self, report: Report, actor, overrides: list[ReportMeasureOverride] | None = None) -> Report:
        if report.status != "draft":
            raise ReportError("Формувати можна тільки чернетку", 409)
        snapshot = self.build(report.program_id, report.period, actor, overrides)
        path = export_root() / f"report-{report.id}-{uuid.uuid4().hex}.json"
        tmp = path.with_suffix(".tmp")
        try:
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
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

    def auto_generate(self, program_id: str, period: str, actor, overrides: list[ReportMeasureOverride] | None = None) -> Report:
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
            return self._save_snapshot(report, actor, overrides)
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


def _status_class(status: str) -> str:
    return {"Виконано": "st-done", "Частково виконано": "st-partial",
            "Не виконано": "st-not"}.get(status, "st-none")


def _fmt_date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _risk_groups(rows):
    """Групує заходи розділу 2 за ризиками, зберігаючи порядок першої появи."""
    groups: list[tuple] = []
    index: dict = {}
    for row in rows:
        key = row.risk.risk_id if row.risk else None
        if key not in index:
            index[key] = len(groups)
            groups.append((row.risk, []))
        groups[index[key]][1].append(row)
    return groups


def csv_export(report: PortalHalfYearReport) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([
        "Розділ", "№ заходу", "ID заходу",
        "Сфера ризику", "Назва ризику", "Опис ризику",
        "Зміст заходу", "Відповідальний підрозділ", "Запланований строк виконання заходу",
        "Індикатор виконання", "Фактичний строк виконання", "Стан виконання",
        "Опис результату виконання заходу або пояснення причин невиконання",
        "Кількість осіб, які взяли участь у навчанні",
        "Індикатор (факт)", "Індикатор (ціль)",
        "Погоджено координатором", "Кількість підтвердних документів", "Зауваження",
    ])
    for section in report.sections:
        for row in section.measures:
            risk = row.risk
            writer.writerow([_safe_csv(val) for val in (
                f"{section.number}. {section.title}",
                row.sequence_number,
                row.measure_id,
                risk.sphere if risk else "",
                risk.title if risk else "",
                risk.description if risk else "",
                row.measure_description,
                row.responsible_department or row.responsible_department_id,
                row.planned_deadline,
                row.completion_indicator,
                _fmt_date(row.factual_date),
                row.execution_status,
                row.result_description,
                row.participants_count if row.participants_count is not None else "",
                row.indicator_actual,
                row.indicator_target,
                "Так" if row.approved_by_coordinator else "Ні",
                row.evidence_count,
                "; ".join(row.warnings),
            )])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def print_html(report: PortalHalfYearReport) -> str:
    """Друкована форма у структурі звіту Порталу доброчесності НАЗК."""
    esc = lambda val: html.escape("" if val is None else str(val), quote=True)

    def block(label, value):
        return f"<div class='lbl'>{esc(label)}</div><div>{esc(value) or '—'}</div>" if value else ""

    def measure_cell(row, section_number):
        name_label = "Найменування заходу" if section_number == 2 else (
            "Навчальний захід" if section_number == 3 else "Опис заходу")
        parts = [block(name_label, row.measure_description),
                 block("Найменування структурного підрозділу, відповідального за виконання заходу"
                       if section_number != 2 else "Відповідальні виконавці",
                       row.responsible_department or row.responsible_department_id),
                 block("Запланований строк виконання заходу", row.planned_deadline)]
        if section_number == 2:
            parts.append(block("Індикатор виконання", row.completion_indicator))
        return "".join(parts)

    def row_markup(row, section_number):
        last = (row.participants_count if row.participants_count is not None else "—") \
            if section_number == 3 else row.result_description
        warn = (f"<div class='warn'>Зауваження: {esc('; '.join(row.warnings))}</div>"
                if row.warnings else "")
        return ("<tr>"
                f"<td class='num'>{esc(row.sequence_number)}</td>"
                f"<td>{measure_cell(row, section_number)}</td>"
                f"<td class='num'>{esc(_fmt_date(row.factual_date))}</td>"
                f"<td class='{_status_class(row.execution_status)}'>{esc(row.execution_status)}</td>"
                f"<td>{esc(last)}{warn}</td>"
                "</tr>")

    sections_markup = []
    for section in report.sections:
        last_header = ("Кількість осіб, які взяли участь у навчанні" if section.number == 3
                       else "Опис результату виконання заходу або пояснення причин невиконання")
        head = ("<table><thead><tr><th class='c-num'>№</th>"
                f"<th>{'Навчальний захід' if section.number == 3 else 'Захід'}</th>"
                "<th class='c-date'>Фактичний строк виконання</th><th class='c-st'>Стан виконання</th>"
                f"<th>{esc(last_header)}</th></tr></thead><tbody>")
        body = []
        if section.number == 2:
            for risk, rows in _risk_groups(section.measures):
                if risk is not None:
                    body.append("<tr class='risk'><td colspan='5'>"
                                + block("Сфера ризику", risk.sphere)
                                + block("Назва ризику", risk.title)
                                + block("Опис ризику", risk.description)
                                + "</td></tr>")
                body.extend(row_markup(r, 2) for r in rows)
        else:
            body.extend(row_markup(r, section.number) for r in section.measures)
        if not body:
            body.append('<tr><td colspan="5">Заходів немає</td></tr>')
        sections_markup.append(f"<h2>{esc(section.title)}</h2>{head}{''.join(body)}</tbody></table>")

    preliminary = ("Попередній стан на дату зрізу, не підсумковий звіт"
                   if report.is_preliminary else "Завершений звітний період")
    scope = "" if report.scope == "program" else f" · Витяг підрозділу {esc(report.department_id)}"
    title = report.period_label or f"Звіт за період {report.period}"
    return ("<!DOCTYPE html><html lang='uk'><head><meta charset='utf-8'>"
            f"<title>{esc(title)}</title>"
            "<style>@page{size:A4 landscape;margin:12mm}"
            "body{font-family:Arial,sans-serif;font-size:11px;color:#111}"
            "h1{font-size:18px;margin:0 0 4px}.org{font-size:13px;margin:0 0 6px}"
            "h2{font-size:14px;margin:24px 0 8px}"
            "table{width:100%;border-collapse:collapse;table-layout:fixed;margin:0 0 18px}"
            "th,td{border:1px solid #b9c0c8;padding:6px;word-wrap:break-word;vertical-align:top}"
            "th{background:#1f4e79;color:#fff;text-align:left}"
            "thead{display:table-header-group}tr{break-inside:avoid}"
            "tbody tr:nth-child(even){background:#f4f6f8}"
            ".c-num{width:4%}.c-date{width:11%}.c-st{width:13%}.num{text-align:center}"
            ".lbl{font-weight:bold;margin-top:4px}.lbl:first-child{margin-top:0}"
            ".risk td{background:#e8eef5}"
            ".st-done{background:#c6efce}.st-partial{background:#ffeb9c}.st-not{background:#ffc7ce}"
            ".warn{margin-top:4px;color:#8a5a00;font-size:10px}"
            "small{color:#555}"
            "@media print{.st-done,.st-partial,.st-not,.risk td,th{-webkit-print-color-adjust:exact;print-color-adjust:exact}}"
            "</style></head><body>"
            f"<h1>{esc(title)}</h1>"
            f"<p class='org'><strong>Орган:</strong> {esc(report.organization_name or '—')}</p>"
            f"<p><small>{esc(report.program_title)} · {preliminary}{scope} · Дані станом на "
            f"{esc(_fmt_date(report.as_of))} · Для друку: Ctrl+P → Зберегти як PDF</small></p>"
            + "".join(sections_markup)
            + "</body></html>")
