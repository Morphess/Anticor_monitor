"""Сторінки перегляду: панель, програма, заходи, ризики, сигнали, звіт, журнал, правила."""
import csv
import io
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from ..auth import SEES_ALL, can_view_measure, current_user, require_role, sees_all
from ..config import UPLOAD_DIR
from ..db import session
from ..models import Evidence, JournalEntry, User
from ..services import monitor, rules
from ..web import render

router = APIRouter(include_in_schema=False)
LEVELS = ["критичний", "високий", "середній", "низький"]


def reminders(measures: list[dict], today) -> dict:
    """Нагадування на дату зрізу: що прострочено і що наближається (за чинним внутрішнім строком)."""
    overdue = [m for m in measures if rules.overdue_today(m["status"], m["deadline_type"], m["internal_deadline"], today)]
    soon = [m for m in measures if rules.due_soon(m["status"], m["deadline_type"], m["internal_deadline"], today)]
    return {"overdue": overdue, "soon": soon}


def visible(user: dict, snap: dict) -> list[dict]:
    return [m for m in snap["measures"] if can_view_measure(user, m)]


@router.get("/panel")
def panel(request: Request, user: dict = Depends(sees_all)):
    snap = monitor.snapshot()
    ms = snap["measures"]
    by_state = Counter(m["portal_state"] for m in ms)
    sections = []
    for sec in snap["sections"]:
        rows = [m for m in ms if m["section"] == sec["code"]]
        sections.append({**sec, "total": len(rows), "states": Counter(m["portal_state"] for m in rows)})
    # Підрозділи — в порядку довідника, без упорядкування «кращий/гірший» (вимога: без рейтингування)
    units = []
    for uid, name in sorted(snap["units"].items()):
        rows = [m for m in ms if m["unit_id"] == uid]
        if rows:
            units.append({"id": uid, "name": name, "total": len(rows),
                          "states": Counter(m["portal_state"] for m in rows),
                          "flags": sum(len(m["flags"]) for m in rows)})
    flag_counts = Counter(f["code"] for f in snap["flags"])
    return render(request, "dashboard.html", user, snap=snap, by_state=by_state, sections=sections, units=units,
                  flag_counts=flag_counts, levels=Counter(r["level"] for r in snap["risks"]), LEVELS=LEVELS,
                  PORTAL_STATES=rules.PORTAL_STATES, rem=reminders(ms, monitor.as_of_date()),
                  queue=sum(1 for m in ms if m["review_state"] == "submitted"))


@router.get("/program")
def program(request: Request, user: dict = Depends(current_user)):
    snap = monitor.snapshot()
    counts = Counter(m["section"] for m in snap["measures"])
    return render(request, "program.html", user, snap=snap, counts=counts)


@router.get("/my")
def my(request: Request, user: dict = Depends(require_role("VYK"))):
    snap = monitor.snapshot()
    ms = visible(user, snap)
    return render(request, "my.html", user, snap=snap, measures=ms, rem=reminders(ms, monitor.as_of_date()))


@router.get("/review")
def review(request: Request, user: dict = Depends(require_role("KOORD"))):
    snap = monitor.snapshot()
    ms = snap["measures"]
    return render(request, "review.html", user, snap=snap,
                  queue=[m for m in ms if m["review_state"] == "submitted"],
                  returned=[m for m in ms if m["review_state"] == "returned"],
                  not_submitted=[m for m in ms if m["review_state"] == "draft"],
                  rem=reminders(ms, monitor.as_of_date()), flags_total=len(snap["flags"]))


@router.get("/measures")
def measures(request: Request, section: str = "", unit: str = "", state: str = "", flag: str = "",
             review: str = "", q: str = "", user: dict = Depends(current_user)):
    snap = monitor.snapshot()
    ms = visible(user, snap)
    if section:
        ms = [m for m in ms if m["section"] == section]
    if unit:
        ms = [m for m in ms if m["unit_id"] == unit]
    if state:
        ms = [m for m in ms if m["portal_state"] == state]
    if review:
        ms = [m for m in ms if m["review_state"] == review]
    if flag:
        ms = [m for m in ms if any(c == flag for c, _ in m["flags"])] if flag != "any" else [m for m in ms if m["flags"]]
    if q.strip():
        needle = q.strip().lower()
        ms = [m for m in ms if needle in m["content"].lower() or needle in m["id"].lower()]
    return render(request, "measures.html", user, snap=snap, measures=ms, PORTAL_STATES=rules.PORTAL_STATES,
                  f={"section": section, "unit": unit, "state": state, "flag": flag, "review": review, "q": q})


@router.get("/measures/{measure_id}")
def measure_detail(request: Request, measure_id: str, user: dict = Depends(current_user)):
    snap = monitor.snapshot()
    m = next((x for x in snap["measures"] if x["id"] == measure_id), None)
    if not m or not can_view_measure(user, m):
        raise HTTPException(404, "Захід не знайдено")
    s = session()
    evidence_ids = [e["id"] for e in m["evidence"]]
    log = s.scalars(select(JournalEntry).where(
        ((JournalEntry.object.in_(("zakhid", "vykonannia"))) & (JournalEntry.object_id == measure_id))
        | ((JournalEntry.object == "pidtverdzhennia") & (JournalEntry.object_id.in_(evidence_ids or [""]))))
        .order_by(JournalEntry.at.desc(), JournalEntry.id.desc())).all()
    risk = next((r for r in snap["risks"] if r["id"] == m["risk_id"]), None)
    own = user["role"] == "VYK" and m["executor_id"] == user["id"]
    return render(request, "measure.html", user, snap=snap, m=m, risk=risk, log=log,
                  can_edit=own and m["review_state"] in rules.EDITABLE_STATES, can_attach=own,
                  can_decide=user["role"] == "KOORD" and m["review_state"] == "submitted",
                  can_postpone=user["role"] == "KOORD" and m["deadline_type"] == "data")


@router.get("/evidence/{evidence_id}/file")
def evidence_file(evidence_id: str, user: dict = Depends(current_user)):
    e = session().get(Evidence, evidence_id)
    if not e or not e.stored_name:
        raise HTTPException(404, "Файл не знайдено")
    if user["role"] not in SEES_ALL and e.uploaded_by_id != user["id"]:
        raise HTTPException(404, "Файл не знайдено")
    path = UPLOAD_DIR / e.stored_name
    if not path.is_file():
        raise HTTPException(404, "Файл не знайдено у сховищі")
    return FileResponse(path, filename=e.original_name or e.stored_name)


@router.get("/risks")
def risks(request: Request, user: dict = Depends(sees_all)):
    snap = monitor.snapshot()
    # Карта ризиків: клітинка (ймовірність, наслідки) -> ризики. Без рейтингування підрозділів.
    cells: dict[tuple[int, int], list[dict]] = {}
    for r in snap["risks"]:
        cells.setdefault((r["probability"], r["impact"]), []).append(r)
    return render(request, "risks.html", user, snap=snap, cells=cells, risk_level=rules.risk_level)


@router.get("/risks/{risk_id}")
def risk_detail(request: Request, risk_id: str, user: dict = Depends(sees_all)):
    snap = monitor.snapshot()
    r = next((x for x in snap["risks"] if x["id"] == risk_id), None)
    if not r:
        raise HTTPException(404, "Ризик не знайдено")
    ms = [m for m in snap["measures"] if m["risk_id"] == risk_id]
    return render(request, "risk.html", user, snap=snap, r=r, measures=ms)


@router.get("/flags")
def flags(request: Request, code: str = "", user: dict = Depends(sees_all)):
    snap = monitor.snapshot()
    rows = [f for f in snap["flags"] if not code or f["code"] == code]
    return render(request, "flags.html", user, snap=snap, rows=rows, code=code,
                  counts=Counter(f["code"] for f in snap["flags"]))


REPORT_COLUMNS = [
    ("rozdil_portal", "Розділ"), ("nomer", "№"), ("opys_zakhodu", "Опис заходу"),
    ("naimenuvannia_pidrozdilu", "Найменування підрозділу"), ("zaplanovanyi_strok", "Запланований строк"),
    ("faktychnyi_strok_vykonannia", "Фактичний строк виконання"), ("stan_vykonannia", "Стан виконання"),
    ("opys_rezultatu_abo_prychyn", "Опис результату або причин невиконання"),
    ("pidtverdni_materialy", "Підтвердні матеріали"),
]


@router.get("/report")
def report(request: Request, user: dict = Depends(sees_all)):
    snap = monitor.snapshot()
    rows = monitor.portal_report(snap)
    pending = [m["id"] for m in snap["measures"] if m["review_state"] != "approved"]
    return render(request, "report.html", user, snap=snap, rows=rows, pending=pending,
                  with_flags=sum(1 for r in rows if r["sluzhbove_sygnaly_pered_perenesenniam"]))


@router.get("/report.csv")
def report_csv(internal: int = 0, user: dict = Depends(sees_all)):
    """Звіт у структурі Порталу. internal=1 додає службові колонки (id заходу, сигнали) — не для перенесення."""
    snap = monitor.snapshot()
    columns = list(REPORT_COLUMNS)
    if internal:
        columns += [("zakhid_id", "ID заходу"), ("sluzhbove_sygnaly_pered_perenesenniam", "Сигнали (службово)")]
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow([title for _, title in columns])
    for row in monitor.portal_report(snap):
        w.writerow([row[key] for key, _ in columns])
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="zvit-{snap["period"]}.csv"'})


@router.get("/journal")
def journal_page(request: Request, obj: str = "", object_id: str = "", who: str = "", page: int = 1,
                 user: dict = Depends(require_role("KOORD", "ADMIN", "ANAL", "KER"))):
    s = session()
    query = select(JournalEntry)
    if obj:
        query = query.where(JournalEntry.object == obj)
    if object_id.strip():
        query = query.where(JournalEntry.object_id == object_id.strip())
    if who.strip():
        query = query.where(JournalEntry.user_id == who.strip())
    page = max(page, 1)
    rows = s.scalars(query.order_by(JournalEntry.at.desc(), JournalEntry.id.desc())
                     .limit(101).offset((page - 1) * 100)).all()
    positions = {u.id: u.position for u in s.scalars(select(User))}
    return render(request, "journal.html", user, rows=rows[:100], more=len(rows) > 100, page=page,
                  positions=positions, f={"obj": obj, "object_id": object_id, "who": who})


@router.get("/rules")
def rules_page(request: Request, user: dict = Depends(current_user)):
    return render(request, "rules.html", user, rules=rules)
