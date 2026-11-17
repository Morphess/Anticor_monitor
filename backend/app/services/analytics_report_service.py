"""Запити керівника до аналітика й аналітичні звіти.

Керівник не має прямого доступу до аналітичних панелей: він надсилає запит,
аналітик готує звіт із висновками й пропозиціями. До звіту додається зріз даних,
обчислений на сервері в момент надсилання; згодом він не змінюється.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ActionLog, AnalyticsReport, AnalyticsRequest, Program, User
from app.services.monitor_service import STATUSES, _fmt, analytics_page

REQUESTER_ROLES = ("KER",)
AUTHOR_ROLES = ("ANAL",)
VIEW_ROLES = ("KER", "ANAL")

REQUEST_STATUSES = {"new": "Нове", "in_progress": "Аналітик готує звіт", "answered": "Звіт надіслано"}
ATTENTION_LIMIT = 15


class ReportError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _who(user: User | None) -> str | None:
    return (user.position or user.login) if user else None


def _log(db: Session, user: User, action: str, entity_type: str, entity_id: int, value: str) -> None:
    db.add(ActionLog(id=str(uuid.uuid4()), occurred_at=datetime.now(), actor_user_id=user.id, action=action,
                     entity_type=entity_type, entity_id=str(entity_id), field_name="status",
                     old_value=None, new_value=value))


# ---------- Зріз даних ----------
def _count(rows: list[dict]) -> dict:
    c = {"done": 0, "review": 0, "rework": 0, "not": 0, "total": len(rows), "overdue": 0, "soon": 0}
    for m in rows:
        c[m["st"]] += 1
        c["overdue"] += m["overdue"]
        c["soon"] += m["due_soon"]
    return c


def _group(rows: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for m in rows:
        groups.setdefault(m[key], []).append(m)
    return [{"name": k, "c": _count(v)} for k, v in groups.items()]


def _share(c: dict) -> int:
    return round(c["done"] * 100 / c["total"]) if c["total"] else 0


def build_snapshot(db: Session, user: User, program_id: str | None, today: date | None = None) -> dict:
    data = analytics_page(db, user, today)
    names = {p["id"]: p["name"] for p in data["programs"]}
    rows = [m for m in data["measures"] if not program_id or m["program_id"] == program_id]
    departments = sorted(_group(rows, "department"), key=lambda g: (_share(g["c"]), -g["c"]["total"]))
    attention = sorted((m for m in rows if m["overdue"] or m["due_soon"]), key=lambda m: m["days_left"])
    return {
        "scope": names.get(program_id, "Усі програми"),
        "period": data["period"],
        "today": data["today"],
        "soon_days": data["soon_days"],
        "statuses": STATUSES,
        "counts": _count(rows),
        "sections": _group(rows, "section"),
        "departments": departments,
        "show_program": not program_id and len(names) > 1,
        "attention": [{
            "n": m["n"], "t": m["t"], "program": names.get(m["program_id"], ""), "department": m["department"],
            "deadline": m["deadline"], "st": m["st"], "overdue": m["overdue"], "days_left": m["days_left"],
        } for m in attention[:ATTENTION_LIMIT]],
        "attention_total": len(attention),
    }


# ---------- Подання для сторінок ----------
def _request_dict(r: AnalyticsRequest, today: date) -> dict:
    return {
        "id": r.id,
        "topic": r.topic,
        "question": r.question,
        "program_id": r.program_id,
        "program": r.program.title if r.program else "Усі програми",
        "due": _fmt(r.due_on),
        "overdue": r.status != "answered" and r.due_on < today,
        "status": r.status,
        "status_label": REQUEST_STATUSES[r.status],
        "requested_by": _who(r.requested_by),
        "requested_at": r.requested_at.strftime("%d.%m.%Y"),
        "analyst": _who(r.analyst),
        "report_id": r.report.id if r.report else None,
    }


def _report_summary(r: AnalyticsReport, viewer: User) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "program": r.program.title if r.program else "Усі програми",
        "created_at": r.created_at.strftime("%d.%m.%Y %H:%M"),
        "author": _who(r.author),
        "request_topic": r.request.topic if r.request else None,
        "unread": viewer.role_id in REQUESTER_ROLES and r.read_at is None,
    }


def inbox(db: Session, user: User, today: date | None = None) -> dict:
    today = today or date.today()
    requests = db.scalars(
        select(AnalyticsRequest)
        .options(selectinload(AnalyticsRequest.program), selectinload(AnalyticsRequest.requested_by),
                 selectinload(AnalyticsRequest.analyst), selectinload(AnalyticsRequest.report))
        .order_by(AnalyticsRequest.requested_at.desc())
    ).all()
    # Спершу те, що чекає дії: нові, потім у роботі, потім виконані
    order = {"new": 0, "in_progress": 1, "answered": 2}
    requests = sorted(requests, key=lambda r: order[r.status])
    reports = db.scalars(
        select(AnalyticsReport)
        .options(selectinload(AnalyticsReport.program), selectinload(AnalyticsReport.author),
                 selectinload(AnalyticsReport.request))
        .order_by(AnalyticsReport.created_at.desc())
    ).all()
    programs = db.scalars(select(Program).order_by(Program.start_date.desc())).all()
    return {
        "role": user.role_id,
        "can_request": user.role_id in REQUESTER_ROLES,
        "can_report": user.role_id in AUTHOR_ROLES,
        "programs": [{"id": p.id, "name": p.title} for p in programs],
        "requests": [_request_dict(r, today) for r in requests],
        "reports": [_report_summary(r, user) for r in reports],
    }


def get_report(db: Session, user: User, report_id: int) -> dict:
    r = db.get(AnalyticsReport, report_id)
    if r is None:
        raise ReportError("Звіт не знайдено", 404)
    data = _report_summary(r, user)
    if user.role_id in REQUESTER_ROLES and r.read_at is None:
        r.read_at = datetime.now()
        db.commit()
    data.update({
        "findings": r.findings,
        "proposals": r.proposals,
        "request_question": r.request.question if r.request else None,
        "snapshot": r.snapshot,
        "unread": False,
    })
    return data


# ---------- Дії ----------
def create_request(db: Session, user: User, topic: str, question: str, program_id: str | None,
                   due_on: date | None, today: date | None = None) -> dict:
    today = today or date.today()
    topic, question = (topic or "").strip(), (question or "").strip()
    if not topic:
        raise ReportError("Вкажіть тему запиту")
    if due_on is None:
        raise ReportError("Вкажіть, до якої дати потрібен звіт")
    if due_on < today:
        raise ReportError("Строк не може бути в минулому")
    if program_id and db.get(Program, program_id) is None:
        raise ReportError("Програму не знайдено")
    r = AnalyticsRequest(topic=topic, question=question, program_id=program_id or None, due_on=due_on,
                         status="new", requested_by_user_id=user.id, requested_at=datetime.now())
    db.add(r)
    db.flush()
    _log(db, user, "Запит аналітичного звіту", "analytics_request", r.id, f"Нове: {topic}")
    db.commit()
    db.refresh(r)
    return _request_dict(r, today)


def take_request(db: Session, user: User, request_id: int) -> dict:
    r = db.get(AnalyticsRequest, request_id)
    if r is None:
        raise ReportError("Запит не знайдено", 404)
    if r.status != "new":
        raise ReportError("Запит уже в роботі або виконаний", 409)
    r.status, r.analyst_user_id, r.taken_at = "in_progress", user.id, datetime.now()
    _log(db, user, "Запит узято в роботу", "analytics_request", r.id, REQUEST_STATUSES["in_progress"])
    db.commit()
    db.refresh(r)
    return _request_dict(r, date.today())


def create_report(db: Session, user: User, request_id: int | None, program_id: str | None, title: str,
                  findings: str, proposals: str) -> dict:
    title, findings, proposals = (title or "").strip(), (findings or "").strip(), (proposals or "").strip()
    request = None
    if request_id is not None:
        request = db.get(AnalyticsRequest, request_id)
        if request is None:
            raise ReportError("Запит не знайдено", 404)
        if request.status == "answered":
            raise ReportError("На цей запит звіт уже надіслано", 409)
    if not title:
        raise ReportError("Вкажіть назву звіту")
    if not findings:
        raise ReportError("Опишіть висновки: що показують дані")
    if program_id and db.get(Program, program_id) is None:
        raise ReportError("Програму не знайдено")

    now = datetime.now()
    report = AnalyticsReport(
        request_id=request.id if request else None, program_id=program_id or None, title=title,
        findings=findings, proposals=proposals, snapshot=build_snapshot(db, user, program_id or None),
        author_user_id=user.id, created_at=now,
    )
    db.add(report)
    if request is not None:
        request.status = "answered"
        if request.analyst_user_id is None:
            request.analyst_user_id, request.taken_at = user.id, now
    db.flush()
    _log(db, user, "Аналітичний звіт надіслано керівнику", "analytics_report", report.id, title)
    db.commit()
    return get_report(db, user, report.id)
