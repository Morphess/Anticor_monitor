"""Read-only analytical dashboard for KER.

All suggestions are transparent rules, NOT automatic management decisions.
The hierarchy and program dispatch use the existing workflow service.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.management_dashboard_repository import ManagementDashboardRepository
from app.schemas.management_dashboard import (
    DepartmentKPI, ManagementDeadline, ManagementDispatch, ManagementMeasure,
    ManagementProgram, ManagementRecommendation, ManagementRecommendationsResponse,
    ManagementRisk, ManagementSummary, ManagementUnit,
)
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError
from app.services.risk_flag_services import detect_risk_flags, period_bounds


class ManagementDashboardError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def default_period(day: date) -> str:
    return f"{day.year}-H{1 if day.month <= 6 else 2}"


def _approved_completed(execution) -> bool:
    return bool(execution and execution.status == "completed"
                and execution.approved_by_coordinator)


def _due(measure, execution, day: date) -> bool:
    return bool(measure.deadline_type == "date" and measure.deadline_on
                and measure.deadline_on < day and not _approved_completed(execution))


def _pending(execution) -> bool:
    return bool(execution and not execution.approved_by_coordinator
                and execution.submitted_at is not None)


@dataclass
class Context:
    department_id: str
    department_name: str
    branch: set[str]
    programs: dict[str, str]
    period: str
    as_of: date
    measures: list
    executions: dict
    evidences: list
    deadline_changes: list
    risks: list
    measurements: list
    covered_risks: set[str]
    department_names: dict[str, str]
    agency: bool = False
    visible_departments: set[str] = None  # кого керівник бачить серед адресатів


RF_RULES = {
    "RF1": ("high", "Прострочений захід", "З'ясувати причини затримки й установити контрольний строк коригувальних дій."),
    "RF2": ("high", "Немає підтвердних матеріалів", "Доручити перевірити підтвердження та обґрунтованість статусу виконання."),
    "RF3": ("high", "Ризик не демонструє очікуваного зниження", "Оцінити дієвість заходу та доцільність коригування плану реагування."),
    "RF4": ("medium", "Формальний опис результату", "Звернути увагу на відсутність вимірюваних результатів; запропонувати уточнення."),
    "RF5": ("high", "Показник нижче цільового", "Перевірити причини недосягнення показника та план коригувальних дій."),
    "RF6": ("high", "Повторні порушення строків", "Проаналізувати системні причини затримок у підрозділі."),
    "RF7a": ("medium", "Дата виконання поза періодом", "Перевірити звітний період та обґрунтованість фактичної дати."),
    "RF7b": ("medium", "Підтвердження датовані пізніше виконання", "Перевірити послідовність дат виконання та документів."),
    "RF7c": ("medium", "Не пояснено невиконання", "Попросити координатора з'ясувати причини невиконання."),
    "RF7d": ("critical", "Високий ризик без заходів", "Розглянути необхідність розроблення заходів для цього ризику."),
    "RF7e": ("low", "Опис внесено завчасно", "Уточнити, чи є відомості фактичним результатом за звітний період."),
    "RF8": ("high", "Номер наказу відсутній у реєстрі", "Перевірити обґрунтованість посилання на наказ."),
}
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class ManagementDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ManagementDashboardRepository(db)

    def _context(self, actor, *, program_id: str | None, period: str, as_of: date) -> Context:
        if actor.role_id != "KER":
            raise ManagementDashboardError("Аналітика керівника доступна лише KER", 403)
        if not actor.department_id:
            raise ManagementDashboardError("Керівнику не призначено підрозділ", 403)
        if not re.fullmatch(r"\d{4}-H[12]", period):
            raise ManagementDashboardError("Період має формат YYYY-H1 або YYYY-H2")
        period_start, _ = period_bounds(period)
        if as_of < period_start:
            raise ManagementDashboardError("Дата зрізу раніше початку вибраного періоду")

        try:
            tree = ProgramWorkflowService(self.db).tree
        except WorkflowError as exc:
            raise ManagementDashboardError(exc.detail, exc.status_code) from exc
        if not tree.exists(actor.department_id):
            raise ManagementDashboardError("Підрозділ керівника не знайдено в ієрархії", 403)

        # Керівник відомства — KER підрозділу без батька: бачить усі створені програми
        # і всі підрозділи. Керівник підрозділу — лише програми, координовані на його
        # підрозділ (або вищий / розіслані окремо нащадку), і свою гілку.
        agency = tree.parents.get(actor.department_id) is None
        if agency:
            branch = set(tree.parents)
            ancestors = branch
            dispatch = {pid: branch for pid in self.repo.all_program_ids()}
        else:
            branch = tree.descendants(actor.department_id)
            ancestors = tree.ancestors(actor.department_id)
            # A program may have been sent to the manager's department, an ancestor,
            # or separately to a descendant. Never use all programs in the system.
            dispatch = self.repo.dispatches(branch | ancestors)
        if program_id is not None:
            if program_id not in dispatch:
                raise ManagementDashboardError("Немає доступу до цієї програми", 403)
            dispatch = {program_id: dispatch[program_id]}

        programs = self.repo.programs(set(dispatch))
        candidates = self.repo.measures(set(programs), branch)
        collabs = self.repo.collaborators({m.id for m in candidates})
        # Відділи, яким доручено захід, теж роблять його видимим керівнику їхньої гілки.
        for mid, units in self.repo.assigned_units({m.id for m in candidates}).items():
            collabs.setdefault(mid, set()).update(units)
        visible = []
        for measure in candidates:
            involved = ({measure.responsible_department_id} | collabs.get(measure.id, set())) & branch
            sent_to = dispatch.get(measure.program_id, set())
            # A relevant department must actually be covered by the program dispatch.
            if any(sent_to & tree.ancestors(dep) for dep in involved):
                visible.append(measure)

        ids = {measure.id for measure in visible}
        linked = {measure.risk_id for measure in visible if measure.risk_id}
        risk_candidates = self.repo.risks(set(programs), branch, linked)
        risks = []
        for risk in risk_candidates:
            if risk.id in linked or (
                risk.owner_department_id in branch
                and bool(dispatch.get(risk.program_id, set()) & tree.ancestors(risk.owner_department_id))
            ):
                risks.append(risk)
        risk_ids = {r.id for r in risks}
        names = self.repo.departments(branch)
        return Context(
            department_id=actor.department_id,
            department_name=names.get(actor.department_id, actor.department_id),
            branch=branch, programs=programs, period=period, as_of=as_of,
            measures=visible, executions=self.repo.executions(ids, period),
            evidences=self.repo.evidences(ids, as_of),
            deadline_changes=self.repo.deadline_changes(ids, as_of),
            risks=risks, measurements=self.repo.measurements(risk_ids, as_of),
            covered_risks=self.repo.all_covered_risks(set(programs)),
            department_names=names,
            agency=agency, visible_departments=branch | ancestors,
        )

    @staticmethod
    def _risk_items(ctx: Context) -> list[ManagementRisk]:
        latest = {}
        for item in ctx.measurements:  # Repository sorts descending by measured_on
            latest.setdefault(item.risk_id, item)
        result = []
        for risk in ctx.risks:
            measurement = latest.get(risk.id)
            value = measurement.value if measurement else None
            baseline = risk.indicator_baseline_value
            target = risk.indicator_target_value
            trend = "no_data"
            reached = None
            if value is not None:
                if value == baseline:
                    trend = "unchanged"
                elif (value < baseline) == (risk.indicator_direction == "decrease"):
                    trend = "improved"
                else:
                    trend = "worsened"
                reached = (value <= target if risk.indicator_direction == "decrease"
                           else value >= target)
            result.append(ManagementRisk(
                program_id=risk.program_id, risk_id=risk.id, title=risk.title,
                level=risk.level, owner_department_id=(risk.owner_department_id
                    if risk.owner_department_id in ctx.branch else None),
                indicator_name=risk.indicator_name,
                indicator_direction=risk.indicator_direction,
                baseline=baseline, target=target,
                actual=value, measured_on=measurement.measured_on if measurement else None,
                trend=trend, target_reached=reached,
                has_measures_in_program=risk.id in ctx.covered_risks,
            ))
        return result

    @staticmethod
    def _deadlines(ctx: Context, horizon_days: int) -> list[ManagementDeadline]:
        items = []
        for measure in ctx.measures:
            execution = ctx.executions.get(measure.id)
            if (measure.deadline_type != "date" or measure.deadline_on is None
                    or _approved_completed(execution)):
                continue
            days = (measure.deadline_on - ctx.as_of).days
            if days > horizon_days:
                continue
            items.append(ManagementDeadline(
                program_id=measure.program_id, measure_id=measure.id,
                description=measure.description,
                responsible_department_id=(measure.responsible_department_id
                    if measure.responsible_department_id in ctx.branch else None),
                deadline_on=measure.deadline_on, days_left=days,
                status=execution.status if execution else "not_started",
                approved=bool(execution and execution.approved_by_coordinator),
                category="overdue" if days < 0 else "upcoming",
            ))
        return sorted(items, key=lambda item: (item.deadline_on, item.program_id, item.measure_id))

    def dashboard(self, actor, *, program_id: str | None, period: str, as_of: date,
                  upcoming_days: int = 14) -> ManagementSummary:
        ctx = self._context(actor, program_id=program_id, period=period, as_of=as_of)
        states = defaultdict(int)
        department_groups = defaultdict(list)
        assigned = self.repo.assigned_units({m.id for m in ctx.measures})
        for measure in ctx.measures:
            ex = ctx.executions.get(measure.id)
            state = ex.status if ex else "not_started"
            states[state] += 1
            dept = measure.responsible_department_id
            # Захід вищого рівня, доручений відділу гілки, рахуємо за цим відділом.
            if dept not in ctx.branch:
                units = sorted(assigned.get(measure.id, set()) & ctx.branch)
                dept = units[0] if units else None
            # For a collaborator outside the branch, do not reveal the foreign department.
            department_groups[dept].append(measure)
        deadlines = self._deadlines(ctx, upcoming_days)
        rows = []
        for dept, measures in sorted(department_groups.items(), key=lambda x: (x[0] is None, x[0] or "")):
            rows.append(DepartmentKPI(
                department_id=dept,
                department_name=(ctx.department_names.get(dept, dept) if dept is not None
                                 else "Заходи співвиконання"),
                total=len(measures),
                approved_completed=sum(_approved_completed(ctx.executions.get(m.id)) for m in measures),
                overdue=sum(_due(m, ctx.executions.get(m.id), as_of) for m in measures),
                awaiting_approval=sum(_pending(ctx.executions.get(m.id)) for m in measures),
            ))
        approved_count = sum(_approved_completed(ctx.executions.get(m.id)) for m in ctx.measures)
        risk_items = self._risk_items(ctx)
        count = len(ctx.measures)
        return ManagementSummary(
            department_id=ctx.department_id, department_name=ctx.department_name,
            scope_department_ids=sorted(ctx.branch), program_ids=sorted(ctx.programs),
            period=period, as_of=as_of, total=count,
            completed=states["completed"], approved_completed=approved_count,
            partial=states["partial"], in_progress=states["in_progress"],
            not_completed=states["not_completed"], not_started=states["not_started"],
            awaiting_approval=sum(_pending(ex) for ex in ctx.executions.values()),
            overdue=sum(item.category == "overdue" for item in deadlines),
            due_soon=sum(item.category == "upcoming" for item in deadlines),
            approved_completion_percent=round(100 * approved_count / count, 1) if count else 0.0,
            high_risks=sum(r.level == "high" for r in risk_items),
            critical_risks=sum(r.level == "critical" for r in risk_items),
            departments=rows,
            scope="agency" if ctx.agency else "department",
        )

    def programs(self, actor, *, period: str, as_of: date) -> list[ManagementProgram]:
        ctx = self._context(actor, program_id=None, period=period, as_of=as_of)
        sends = [row for row in self.repo.program_dispatch_rows(set(ctx.programs))
                 if row[1] in ctx.visible_departments]
        programs = self.repo.program_rows(set(ctx.programs))
        names = self.repo.departments({row[1] for row in sends} | {
            p.coordinator_department_id for p in programs if p.coordinator_department_id})
        counts = defaultdict(int)
        for measure in ctx.measures:
            counts[measure.program_id] += 1
        result = []
        for program in programs:
            seen, recipients = set(), []
            for pid, dep, sent_at in sends:
                if pid == program.id and dep not in seen:
                    seen.add(dep)
                    recipients.append(ManagementDispatch(
                        department_id=dep, department_name=names.get(dep, dep), sent_at=sent_at))
            coord = program.coordinator_department_id
            result.append(ManagementProgram(
                id=program.id, title=program.title,
                start_date=program.start_date, end_date=program.end_date,
                coordinator_department_id=coord,
                coordinator_department_name=names.get(coord, coord) if coord else None,
                dispatched_to=recipients, measures_total=counts[program.id],
            ))
        return result

    def measures(self, actor, *, program_id: str | None, period: str,
                 as_of: date) -> list[ManagementMeasure]:
        ctx = self._context(actor, program_id=program_id, period=period, as_of=as_of)
        sections = self.repo.sections({m.section_id for m in ctx.measures if m.section_id})
        units = {} if ctx.agency else self.repo.assigned_units({m.id for m in ctx.measures})
        names = self.repo.departments(ctx.visible_departments)
        result = []
        for measure in ctx.measures:
            ex = ctx.executions.get(measure.id)
            section = sections.get(measure.section_id)
            dept = measure.responsible_department_id
            if dept not in ctx.visible_departments:
                dept = None  # співвиконання поза гілкою: чужий підрозділ не розкриваємо
            unit_ids = sorted(u for u in units.get(measure.id, set()) if u in ctx.branch)
            result.append(ManagementMeasure(
                program_id=measure.program_id,
                program_title=ctx.programs.get(measure.program_id, measure.program_id),
                section_id=measure.section_id,
                section_number=section.number if section else None,
                section_title=section.title if section else None,
                measure_id=measure.id, sequence_number=measure.sequence_number,
                description=measure.description,
                responsible_department_id=dept,
                responsible_department_name=names.get(dept, dept) if dept else None,
                assigned_units=[ManagementUnit(department_id=u, department_name=names.get(u, u))
                                for u in unit_ids],
                deadline_type=measure.deadline_type, deadline_on=measure.deadline_on,
                deadline_description=measure.deadline_description,
                status=ex.status if ex else "not_started",
                approved=bool(ex and ex.approved_by_coordinator),
                submitted_at=ex.submitted_at if ex else None,
                completed_on=ex.completed_on if ex else None,
                indicator_target=measure.indicator_target,
                indicator_actual=ex.indicator_actual if ex else None,
            ))
        return result

    def deadlines(self, actor, *, program_id: str | None, period: str,
                  as_of: date, horizon_days: int = 14) -> list[ManagementDeadline]:
        return self._deadlines(self._context(actor, program_id=program_id, period=period,
                                             as_of=as_of), horizon_days)

    def risks(self, actor, *, program_id: str | None, period: str,
              as_of: date) -> list[ManagementRisk]:
        return self._risk_items(self._context(actor, program_id=program_id, period=period,
                                              as_of=as_of))

    def recommendations(self, actor, *, program_id: str | None, period: str,
                        as_of: date, limit: int = 100) -> ManagementRecommendationsResponse:
        ctx = self._context(actor, program_id=program_id, period=period, as_of=as_of)
        signals: dict[str, ManagementRecommendation] = {}

        def add(code: str, pid: str, objtype: str, oid: str, priority: str,
                title: str, reason: str, suggestion: str, source: str = "operational") -> None:
            key = f"{pid}:{code}:{objtype}:{oid}"
            signals[key] = ManagementRecommendation(
                key=key, code=code, program_id=pid, object_type=objtype,
                object_id=str(oid), priority=priority, title=title,
                reason=reason, suggestion=suggestion, source=source,
                as_of=ctx.as_of,
            )

        ev_ids = {ev.measure_id for ev in ctx.evidences
                  if ev.uploaded_at is None or ev.uploaded_at.date() <= as_of}
        for measure in ctx.measures:
            ex = ctx.executions.get(measure.id)
            if _due(measure, ex, as_of):
                days = (as_of - measure.deadline_on).days
                add("DL_OVERDUE", measure.program_id, "zakhid", measure.id,
                    "critical" if days >= 14 else "high", "Прострочено строк виконання",
                    f"Строк {measure.deadline_on}; прострочення {days} дн.; "
                    f"стан {ex.status if ex else 'not_started'}; погоджене виконання відсутнє.",
                    "Перевірити причини затримки та проконтролювати коригувальні дії.")
            elif measure.deadline_type == "date" and measure.deadline_on and not _approved_completed(ex):
                left = (measure.deadline_on - as_of).days
                if 0 <= left <= 7:
                    add("DL_SOON", measure.program_id, "zakhid", measure.id,
                        "high" if left <= 3 else "medium", "Наближається строк виконання",
                        f"До дедлайну {measure.deadline_on} залишилося {left} дн.",
                        "Звернути увагу на готовність заходу та необхідні підтвердження.")
            if _pending(ex):
                add("EX_APPROVAL", measure.program_id, "zakhid", measure.id,
                    "medium", "Виконання очікує погодження",
                    f"Стан {ex.status}; подано {ex.submitted_at}; погодження KOORD відсутнє.",
                    "Перевірити, чи координатор розглянув поданий результат.")
            if ex and ex.status in {"completed", "partial"} and measure.id not in ev_ids:
                add("EV_MISSING", measure.program_id, "zakhid", measure.id,
                    "high", "Немає підтвердних матеріалів",
                    f"Стан заходу {ex.status}, але підтвердження відсутнє на дату зрізу.",
                    "Перевірити достатність доказів та обґрунтованість статусу.")
            if (ex and ex.status in {"completed", "partial"}
                    and ex.indicator_actual is not None and measure.indicator_target is not None
                    and Decimal(str(ex.indicator_actual)) < Decimal(str(measure.indicator_target))):
                add("INDICATOR_BELOW", measure.program_id, "zakhid", measure.id,
                    "high", "Фактичний показник нижче цілі",
                    f"Факт {ex.indicator_actual}; ціль {measure.indicator_target}.",
                    "Проконтролювати план досягнення цільового значення.")

        for risk in self._risk_items(ctx):
            if risk.level in {"high", "critical"} and not risk.has_measures_in_program:
                add("RISK_NO_MEASURES", risk.program_id, "ryzyk", risk.risk_id,
                    "critical", "Високий ризик без заходів реагування",
                    f"Рівень {risk.level}; в програмі відсутні заходи, пов'язані з цим ризиком.",
                    "Звернути увагу на необхідність розроблення заходів реагування.")
            if risk.trend == "worsened":
                add("RISK_WORSENED", risk.program_id, "ryzyk", risk.risk_id,
                    "high", "Показник ризику погіршився",
                    f"Базове значення {risk.baseline}, поточне {risk.actual}; "
                    f"бажаний напрям {risk.indicator_direction}.",
                    "Перевірити ефективність заходів щодо зменшення ризику.")
            elif risk.level in {"high", "critical"} and risk.trend == "no_data":
                add("RISK_UNMEASURED", risk.program_id, "ryzyk", risk.risk_id,
                    "medium", "Немає актуального вимірювання високого ризику",
                    f"Рівень {risk.level}; немає вимірювань станом на {as_of}.",
                    "Звернути увагу на необхідність вимірювання індикатора ризику.")

        # Optional earlier modules: RF8 rejected-order journal and order-version alerts.
        # A missing migration does not break the KER dashboard.
        period_start, period_end = period_bounds(period)
        ids = {m.id for m in ctx.measures}
        rejected = defaultdict(list)
        for event in self.repo.optional_event_rows("invalid_order_references", ids):
            happened = event["attempted_at"].date()
            if period_start <= happened <= min(as_of, period_end):
                rejected[event["measure_id"]].append((happened, event["order_number"]))
        measure_program = {m.id: m.program_id for m in ctx.measures}
        for mid, attempts in rejected.items():
            numbers = {number for _day, number in attempts}
            last_day = max(day for day, _number in attempts)
            add("RF8", measure_program[mid], "zakhid", mid, "high",
                "Звернути увагу на відхилений номер наказу",
                f"Остання спроба {last_day}; відхилених посилань {len(attempts)}; "
                f"номери: {', '.join(sorted(numbers))}.",
                "Перевірити, чому виконавець послався на наказ, якого немає в реєстрі.",
                "risk_flag")
        for alert in self.repo.optional_event_rows("order_change_alerts", ids):
            if alert["created_at"].date() > as_of:
                continue
            mid = alert["measure_id"]
            approved = bool(alert.get("has_approved_execution"))
            add("DOC_CHANGED", measure_program[mid], "order_change_alert", str(alert["id"]),
                "high" if approved else "medium",
                "Змінено наказ, використаний як підтвердження",
                f"Захід {mid}; повідомлення #{alert['id']}; Evidence {alert['evidence_id']}; "
                f"стара версія #{alert['previous_version_id']}, "
                f"нова #{alert['new_version_id']}; "
                f"погодження на момент зміни: {'так' if approved else 'ні'}.",
                "Звернути увагу на доцільність повторної перевірки документа координатором.")

        # For a completed reporting period, use the existing deterministic RF engine.
        period_start, period_end = period_bounds(period)
        if as_of >= period_end:
            for pid in ctx.programs:
                program_measures = [m for m in ctx.measures if m.program_id == pid]
                measures_ids = {m.id for m in program_measures}
                linked_ids = {m.risk_id for m in program_measures if m.risk_id}
                relevant_risks = [r for r in ctx.risks if r.program_id == pid and (
                    r.id in linked_ids or
                    (r.id not in ctx.covered_risks and r.owner_department_id in ctx.branch)
                )]
                visible_risk_ids = {r.id for r in relevant_risks}
                snapshot = {
                    "measures": program_measures,
                    "executions": [e for mid, e in ctx.executions.items() if mid in measures_ids],
                    "evidences": [e for e in ctx.evidences if e.measure_id in measures_ids],
                    "deadline_changes": [d for d in ctx.deadline_changes if d.measure_id in measures_ids],
                    "risks": relevant_risks,
                    "measurements": [r for r in ctx.measurements if
                                     r.risk_id in visible_risk_ids and period_start <= r.measured_on <= period_end],
                }
                for flag in detect_risk_flags(period=period, as_of=as_of, **snapshot):
                    if flag.object_type == "zakhid" and flag.object_id not in measures_ids:
                        continue
                    if flag.object_type == "ryzyk" and flag.object_id not in visible_risk_ids:
                        continue
                    if flag.object_type == "pidrozdil" and flag.object_id not in ctx.branch:
                        continue
                    if flag.code not in RF_RULES:
                        continue
                    priority, title, suggestion = RF_RULES[flag.code]
                    add(flag.code, pid, flag.object_type, flag.object_id,
                        priority, title, f"{flag.message}. {flag.explanation}",
                        suggestion, "risk_flag")

        ordered = sorted(signals.values(), key=lambda r: (
            PRIORITY_ORDER[r.priority], r.program_id, r.code, r.object_id
        ))
        return ManagementRecommendationsResponse(
            department_id=ctx.department_id, period=period, as_of=as_of,
            total=len(ordered), recommendations=ordered[:limit],
        )
