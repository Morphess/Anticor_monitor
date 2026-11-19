"""Аналітика поточного зрізу для MAIN_KOORD/KOORD та особистого кабінету VYK.

Правила доступу — ті самі, що у ProgramWorkflowService. Жодного запису в БД.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.dashboard import (
    DashboardSummary, DepartmentDashboard, DepartmentProgress,
    RiskDashboard, RiskIndicator, DeadlineDashboard, DeadlineItem, MyDashboard,
)
from app.services.program_workflow_services import ProgramWorkflowService


COMPLETED = "completed"
VALID_ROLES = frozenset({"MAIN_KOORD", "KOORD", "VYK"})


class DashboardError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.status_code = status_code


def half_year(date_value: date) -> str:
    return f"{date_value.year}-H{1 if date_value.month <= 6 else 2}"


def validate_period(period: str) -> None:
    if not re.fullmatch(r"\d{4}-H[12]", period):
        raise DashboardError("Період має формат YYYY-H1 або YYYY-H2")


def is_approved_completed(execution) -> bool:
    return bool(execution and execution.status == COMPLETED
                and execution.approved_by_coordinator)


def is_overdue(measure, execution, as_of: date) -> bool:
    # Прострочено: строк уже минув і немає погодженого виконання.
    return bool(measure.deadline_type == "date" and measure.deadline_on
                and measure.deadline_on < as_of and not is_approved_completed(execution))


def is_upcoming(measure, execution, as_of: date, days: int) -> bool:
    return bool(measure.deadline_type == "date" and measure.deadline_on
                and as_of <= measure.deadline_on <= as_of + timedelta(days=days)
                and not is_approved_completed(execution))


@dataclass
class Scope:
    program_id: str
    program_title: str
    scope: str
    measures: list
    executions: dict
    risk_department_ids: set[str] | None


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DashboardRepository(db)
        self.workflow = ProgramWorkflowService(db)

    def _scope(self, program_id: str, actor, period: str) -> Scope:
        validate_period(period)
        if actor.role_id not in VALID_ROLES:
            raise DashboardError("Немає доступу до Dashboard", 403)
        # visible_program перевіряє програму, авторство, направлення і призначення.
        program = self.workflow.visible_program(program_id, actor)
        visible = self.workflow.program_measures(program_id, actor)
        ids = {row["id"] for row in visible}
        measures = self.repo.measures(program_id, ids)
        executions = self.repo.executions({m.id for m in measures}, period)
        department_ids = None
        if actor.role_id == "KOORD":
            if not actor.department_id:
                raise DashboardError("Для KOORD не визначено підрозділ", 403)
            department_ids = self.workflow.tree.descendants(actor.department_id)
            if not department_ids:
                raise DashboardError("Підрозділ відсутній в ієрархії", 403)
        return Scope(
            program_id=program.id, program_title=program.title,
            scope={"MAIN_KOORD": "program", "KOORD": "department", "VYK": "executor"}[actor.role_id],
            measures=measures, executions=executions, risk_department_ids=department_ids,
        )

    @staticmethod
    def _summary(scope: Scope, *, period: str, as_of: date, upcoming_days: int) -> DashboardSummary:
        counters = {name: 0 for name in (
            "completed", "approved_completed", "partial", "in_progress",
            "not_completed", "not_started", "unapproved", "overdue", "due_soon"
        )}
        for measure in scope.measures:
            execution = scope.executions.get(measure.id)
            state = execution.status if execution else "not_started"
            if state not in {"completed", "partial", "in_progress", "not_completed", "not_started"}:
                state = "not_started"
            counters[state] += 1
            if execution and not execution.approved_by_coordinator:
                counters["unapproved"] += 1
            if is_approved_completed(execution):
                counters["approved_completed"] += 1
            if is_overdue(measure, execution, as_of):
                counters["overdue"] += 1
            if is_upcoming(measure, execution, as_of, upcoming_days):
                counters["due_soon"] += 1
        count = len(scope.measures)
        return DashboardSummary(
            program_id=scope.program_id, program_title=scope.program_title,
            scope=scope.scope, period=period, as_of=as_of, total=count,
            completion_percent=round(100 * counters["completed"] / count, 1) if count else 0,
            approved_completion_percent=round(100 * counters["approved_completed"] / count, 1) if count else 0,
            upcoming_days=upcoming_days, **counters,
        )

    def summary(self, program_id: str, actor, *, period: str, as_of: date,
                upcoming_days: int = 14) -> DashboardSummary:
        scope = self._scope(program_id, actor, period)
        return self._summary(scope, period=period, as_of=as_of, upcoming_days=upcoming_days)

    def departments(self, program_id: str, actor, *, period: str, as_of: date) -> DepartmentDashboard:
        scope = self._scope(program_id, actor, period)
        groups: dict[str | None, list] = defaultdict(list)
        for measure in scope.measures:
            # Кожен захід один раз — у відповідального підрозділу.
            # Співвиконавців не дублюємо для підрахунку загального прогресу.
            groups[measure.responsible_department_id].append(measure)
        titles = self.repo.departments({k for k in groups if k is not None})
        rows = []
        for department_id, measures in groups.items():
            count = len(measures)
            complete = sum(scope.executions.get(m.id) is not None and
                           scope.executions[m.id].status == COMPLETED for m in measures)
            approved = sum(is_approved_completed(scope.executions.get(m.id)) for m in measures)
            overdue = sum(is_overdue(m, scope.executions.get(m.id), as_of) for m in measures)
            rows.append(DepartmentProgress(
                department_id=department_id,
                department_name=titles.get(department_id, department_id or "Без відповідального підрозділу"),
                total=count, completed=complete, approved_completed=approved,
                overdue=overdue, completion_percent=round(100 * complete / count, 1) if count else 0,
            ))
        rows.sort(key=lambda r: (r.department_id is None, r.department_id or ""))
        return DepartmentDashboard(program_id=program_id, period=period, as_of=as_of, departments=rows)

    def _risks(self, scope: Scope, *, as_of: date) -> RiskDashboard:
        linked_ids = {m.risk_id for m in scope.measures if m.risk_id}
        if scope.scope == "program":
            allowed_risks = None
            owned_depts = None
        elif scope.scope == "department":
            allowed_risks = linked_ids
            owned_depts = scope.risk_department_ids
        else:
            allowed_risks = linked_ids
            owned_depts = None
        risks = self.repo.risks(scope.program_id, allowed_risk_ids=allowed_risks,
                                owned_department_ids=owned_depts)
        measurements = self.repo.latest_measurements({r.id for r in risks}, as_of)
        globally_covered = self.repo.risk_ids_covered_by_program(scope.program_id)
        result = []
        for risk in risks:
            latest = measurements.get(risk.id)
            actual = latest.value if latest else None
            baseline = Decimal(str(risk.indicator_baseline_value))
            target = Decimal(str(risk.indicator_target_value))
            trend = "no_data"
            reached = None
            progress = None
            if actual is not None:
                current = Decimal(str(actual))
                improved = (current < baseline if risk.indicator_direction == "decrease"
                            else current > baseline)
                worsened = (current > baseline if risk.indicator_direction == "decrease"
                            else current < baseline)
                trend = "improved" if improved else "worsened" if worsened else "unchanged"
                reached = current <= target if risk.indicator_direction == "decrease" else current >= target
                if target != baseline:
                    progress = round(float((current - baseline) * 100 / (target - baseline)), 1)
            result.append(RiskIndicator(
                risk_id=risk.id, title=risk.title, level=risk.level,
                owner_department_id=risk.owner_department_id,
                indicator_name=risk.indicator_name, indicator_unit=risk.indicator_unit,
                indicator_direction=risk.indicator_direction, baseline=baseline, target=target,
                current=actual, measured_on=latest.measured_on if latest else None,
                progress_percent=progress, trend=trend, target_reached=reached,
                has_measures_in_program=risk.id in globally_covered,
            ))
        return RiskDashboard(
            program_id=scope.program_id, as_of=as_of, total=len(result),
            high=sum(r.level == "high" for r in result),
            critical=sum(r.level == "critical" for r in result),
            unmeasured=sum(r.trend == "no_data" for r in result),
            without_measures=sum(not r.has_measures_in_program for r in result),
            risks=result,
        )

    def risks(self, program_id: str, actor, *, period: str, as_of: date) -> RiskDashboard:
        return self._risks(self._scope(program_id, actor, period), as_of=as_of)

    @staticmethod
    def _deadlines(scope: Scope, *, period: str, as_of: date,
                   horizon_days: int, limit: int) -> DeadlineDashboard:
        overdue, upcoming = [], []
        for m in scope.measures:
            execution = scope.executions.get(m.id)
            if not (is_overdue(m, execution, as_of) or is_upcoming(m, execution, as_of, horizon_days)):
                continue
            item = DeadlineItem(
                measure_id=m.id, description=m.description,
                deadline_on=m.deadline_on, days_until=(m.deadline_on - as_of).days,
                responsible_department_id=m.responsible_department_id,
                execution_status=execution.status if execution else "not_started",
                approved_by_coordinator=bool(execution and execution.approved_by_coordinator),
            )
            if item.days_until < 0:
                overdue.append(item)
            else:
                upcoming.append(item)
        overdue.sort(key=lambda item: (item.deadline_on, item.measure_id))
        upcoming.sort(key=lambda item: (item.deadline_on, item.measure_id))
        return DeadlineDashboard(
            program_id=scope.program_id, period=period, as_of=as_of,
            horizon_days=horizon_days, overdue_total=len(overdue),
            upcoming_total=len(upcoming), overdue=overdue[:limit], upcoming=upcoming[:limit],
        )

    def deadlines(self, program_id: str, actor, *, period: str, as_of: date,
                  horizon_days: int = 14, limit: int = 50) -> DeadlineDashboard:
        scope = self._scope(program_id, actor, period)
        return self._deadlines(scope, period=period, as_of=as_of,
                               horizon_days=horizon_days, limit=limit)

    def my(self, program_id: str, actor, *, period: str, as_of: date,
           horizon_days: int = 14, limit: int = 50) -> MyDashboard:
        if actor.role_id != "VYK":
            raise DashboardError("Особистий кабінет доступний лише VYK", 403)
        scope = self._scope(program_id, actor, period)
        return MyDashboard(
            summary=self._summary(scope, period=period, as_of=as_of, upcoming_days=horizon_days),
            deadlines=self._deadlines(scope, period=period, as_of=as_of,
                                      horizon_days=horizon_days, limit=limit),
            risks=self._risks(scope, as_of=as_of),
        )
