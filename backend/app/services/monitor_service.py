"""Дані для сторінок виконавця й координатора з таблиць програми.

Статус заходу — це запис executions за поточний звітний період (півріччя):
  done   — виконання подано й погоджено координатором;
  review — виконання подано (наказ знайдено), чекає погодження;
  rework — координатор повернув на доопрацювання;
  not    — запису немає або захід не виконано.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Department, Execution, Measure, MeasureCollaborator, Order, Program, User

STATUSES = {
    "done": "Виконано",
    "review": "На розгляді",
    "rework": "На доопрацюванні",
    "not": "Не виконано",
}

# Як статус сторінки записується в executions
_TO_EXECUTION = {
    "done": ("completed", True),
    "review": ("completed", False),
    "rework": ("in_progress", False),
    "not": ("not_completed", False),
}

EDITOR_ROLES = ("ADMIN", "KOORD")


class MonitorError(Exception):
    def __init__(self, message: str, status_code: int = 404):
        super().__init__(message)
        self.status_code = status_code


def current_period(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year}-H{1 if today.month <= 6 else 2}"


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _execution(measure: Measure, period: str) -> Execution | None:
    return next((e for e in measure.executions if e.period == period), None)


def _status_key(execution: Execution | None) -> str:
    if execution is None:
        return "not"
    if execution.status == "completed":
        return "done" if execution.approved_by_coordinator else "review"
    if execution.status == "in_progress" and execution.status_label == STATUSES["rework"]:
        return "rework"
    if execution.status in ("in_progress", "partial"):
        return "review"
    return "not"


def _measure_query():
    return select(Measure).options(
        selectinload(Measure.executions),
        selectinload(Measure.orders),
        selectinload(Measure.responsible_department),
        selectinload(Measure.collaborators).selectinload(MeasureCollaborator.department),
        selectinload(Measure.section),
        selectinload(Measure.program),
    )


def _department_name(db: Session, department_id: str | None) -> str | None:
    if not department_id:
        return None
    dep = db.get(Department, department_id)
    return dep.name if dep else department_id


# ---------- Виконавець ----------
def _executor_measures(db: Session, user: User):
    conditions = [Measure.assigned_user_id == user.id]
    if user.department_id:
        conditions.append(Measure.responsible_department_id == user.department_id)
    query = _measure_query().where(or_(*conditions))
    if user.program_id:
        query = query.where(Measure.program_id == user.program_id)
    return db.scalars(query.order_by(Measure.section_id, Measure.sequence_number)).all()


def executor_page(db: Session, user: User) -> dict:
    period = current_period()
    today = date.today()
    rows = []
    for m in _executor_measures(db, user):
        execution = _execution(m, period)
        st = _status_key(execution)
        order = m.orders[0] if m.orders else None
        label = STATUSES[st].lower()
        if st == "not" and m.deadline_on and m.deadline_on < today:
            label = "строк минув"
        indicator = m.completion_indicator
        if m.indicator_target is not None:
            indicator += f" — ціль {m.indicator_target.normalize():f}{' ' + m.indicator_unit if m.indicator_unit else ''}"
        rows.append({
            "id": m.id,
            "order_title": order.title if order else m.description,
            "organ": m.program.organization_name,
            "start": _fmt(m.program.start_date),
            "end": _fmt(m.deadline_on) if m.deadline_on else m.deadline_description,
            "entered": order.number if order and st in ("done", "review") else "",
            "st": st,
            "status": label,
            "goal": m.description if order else m.completion_indicator,
            "indicator": indicator if order else "",
            "note": "Підтвердження: " + m.required_evidence,
        })
    unit = _department_name(db, user.department_id) or user.position or user.login
    return {"unit": unit, "rows": rows}


def check_order(db: Session, user: User, measure_id: str, number: str) -> dict:
    """Виконавець увів номер наказу. Успіх — наказ є в реєстрі й належить саме цьому заходу."""
    number = (number or "").replace("№", "").strip()
    measure = next((m for m in _executor_measures(db, user) if m.id == measure_id), None)
    if measure is None:
        return {"ok": False, "message": "Захід не знайдено серед ваших заходів"}
    if not number:
        return {"ok": False, "message": "Введіть номер наказу"}
    orders = db.scalars(select(Order).where(Order.number == number)).all()
    if not orders:
        return {"ok": False, "message": f"Помилка: наказу № {number} немає в реєстрі"}
    order = next((o for o in orders if o.measure_id == measure_id), None)
    if order is None:
        return {"ok": False, "message": f"Помилка: № {number} — це наказ до іншого заходу («{orders[0].title}»)"}

    period = current_period()
    execution = db.get(Execution, (measure_id, period))
    if execution is not None and _status_key(execution) == "done":
        return {"ok": True, "message": "Захід уже погоджено", "st": "done", "status": "виконано"}
    if execution is None:
        execution = Execution(measure_id=measure_id, period=period)
        db.add(execution)
    execution.status = "completed"
    execution.status_label = STATUSES["review"]
    execution.completed_on = order.issued_on or date.today()
    execution.result_description = f"Наказ № {order.number}: {order.title}"
    execution.submitted_by_user_id = user.id
    execution.submitted_at = datetime.now()
    execution.approved_by_coordinator = False
    db.commit()
    return {"ok": True, "message": "Успіх — передано координатору", "st": "review", "status": "на розгляді"}


# ---------- Координатор ----------
def coordinator_page(db: Session, user: User) -> dict:
    period = current_period()
    programs = db.scalars(select(Program).order_by(Program.start_date.desc())).all()
    measures = db.scalars(_measure_query().order_by(Measure.section_id, Measure.sequence_number)).all()
    by_program: dict[str, list[Measure]] = {}
    for m in measures:
        by_program.setdefault(m.program_id, []).append(m)

    result = []
    for p in programs:
        sections: dict[str, dict] = {}
        for m in by_program.get(p.id, []):
            sec = sections.setdefault(m.section_id, {
                "n": m.section.number, "title": m.section.title, "items": [], "_deadlines": []})
            if m.deadline_on:
                sec["_deadlines"].append(m.deadline_on)
            execution = _execution(m, period)
            st = _status_key(execution)
            order = m.orders[0] if m.orders else None
            organs = [m.responsible_department.name] if m.responsible_department else []
            organs += [c.department.name for c in m.collaborators]
            sec["items"].append({
                "n": f"{m.section.number}.{m.sequence_number}",
                "measure_id": m.id,
                "t": m.description,
                "d": _fmt(m.deadline_on) if m.deadline_on else m.deadline_description,
                "units": [{
                    "organ": ", ".join(organs) or "Підрозділ не призначено",
                    "date": _fmt(execution.completed_on) if execution and execution.completed_on else "—",
                    "order": order.number if order else "",
                    "link": (order.document_url or "#") if order else "#",
                    "st": st,
                }],
            })
        section_list = []
        for sec in sorted(sections.values(), key=lambda s: s["n"]):
            deadlines = sec.pop("_deadlines")
            sec["deadline"] = _fmt(max(deadlines)) if deadlines else "—"
            section_list.append(sec)
        result.append({
            "id": p.id,
            "name": p.title,
            "start": _fmt(p.start_date),
            "end": _fmt(p.end_date),
            "sections": section_list,
        })
    unit = _department_name(db, user.department_id) or user.position or user.login
    return {"unit": unit, "programs": result, "statuses": STATUSES, "can_edit": user.role_id in EDITOR_ROLES}


def set_status(db: Session, user: User, measure_id: str, status: str) -> dict:
    if status not in STATUSES:
        raise MonitorError("Невідомий статус", 400)
    if db.get(Measure, measure_id) is None:
        raise MonitorError("Захід не знайдено")
    period = current_period()
    execution = db.get(Execution, (measure_id, period))
    if execution is None:
        execution = Execution(measure_id=measure_id, period=period, result_description="")
        db.add(execution)
    execution.status, execution.approved_by_coordinator = _TO_EXECUTION[status]
    execution.status_label = STATUSES[status]
    if status == "done" and execution.completed_on is None:
        execution.completed_on = date.today()
    db.commit()
    return {"status": status, "label": STATUSES[status]}
