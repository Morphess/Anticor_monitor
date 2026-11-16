"""Стан програми за звітний період: заходи з виконанням, підтвердженнями, станом для Порталу й сигналами,
ризики з рівнем і прогресом індикатора. Усі висновки рахують чисті правила з rules.py —
тут лише збирання даних із бази в словники для сторінок, звіту й API."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import session
from ..models import Measure, Program, Risk, Section, Setting, Unit, User
from ..utils import period_bounds
from . import rules


# ---------- налаштування ----------
def get_setting(key: str, default=None):
    row = session().get(Setting, key)
    return row.value.get("value", default) if row else default


def set_setting(key: str, value) -> None:
    s = session()
    row = s.get(Setting, key)
    if row:
        row.value = {"value": value}
    else:
        s.add(Setting(key=key, value={"value": value}))


def current_period() -> str:
    return get_setting("period", "2026-H1")


def as_of_date() -> date:
    """Дата зрізу даних: «сьогодні» для нагадувань і підписів. Задається координатором або адміністратором."""
    value = get_setting("as_of")
    return date.fromisoformat(value) if value else date.today()


# ---------- знімок стану ----------
def _execution_dict(e) -> dict:
    if e is None:
        return {"exists": False, "status": "ne_rozpochato", "actual_date": None, "result_text": "",
                "indicator_fact": None, "review_state": "draft", "review_comment": "", "entered_by": None,
                "entered_at": None, "reviewed_by": None, "reviewed_at": None}
    return {"exists": True, "status": e.status, "actual_date": e.actual_date, "result_text": e.result_text or "",
            "indicator_fact": e.indicator_fact, "review_state": e.review_state,
            "review_comment": e.review_comment or "", "entered_by": e.entered_by_id, "entered_at": e.entered_at,
            "reviewed_by": e.reviewed_by_id, "reviewed_at": e.reviewed_at}


def risk_value_at(risk: Risk, on: date) -> tuple[float, date | None]:
    """Останнє виміряне значення індикатора ризику на дату (якщо вимірювань немає — базове)."""
    past = [m for m in risk.measurements if m.date <= on]
    return (past[-1].value, past[-1].date) if past else (risk.indicator_base, None)


def snapshot(period: str | None = None) -> dict:
    """Повний стан програми за півріччя. Детермінований: залежить лише від даних у базі та періоду."""
    period = period or current_period()
    period_start, period_end = period_bounds(period)
    s = session()
    units = {u.id: u.name for u in s.scalars(select(Unit))}
    sections = {x.code: x for x in s.scalars(select(Section))}
    positions = {u.id: u.position for u in s.scalars(select(User))}

    risks_rows = list(s.scalars(select(Risk).options(selectinload(Risk.measurements)).order_by(Risk.id)))
    risks: dict[str, dict] = {}
    for r in risks_rows:
        current, measured_on = risk_value_at(r, period_end)
        score = rules.risk_score(r.probability, r.impact)
        risks[r.id] = {
            "id": r.id, "function": r.function, "name": r.name, "content": r.content, "sources": r.sources,
            "existing_controls": r.existing_controls, "probability": r.probability, "impact": r.impact,
            "score": score, "level": rules.risk_level(score), "owner_unit_id": r.owner_unit_id,
            "owner_unit": units.get(r.owner_unit_id, ""), "indicator_name": r.indicator_name,
            "indicator_unit": r.indicator_unit, "direction": r.direction, "base": r.indicator_base,
            "current": current, "measured_on": measured_on, "target": r.indicator_target,
            "target_date": r.target_date,
            "progress": rules.risk_progress(r.indicator_base, current, r.indicator_target),
            "measurements": [{"date": m.date, "value": m.value, "source": m.source} for m in r.measurements],
            "measures": [], "flags": [],
        }

    rows = s.scalars(select(Measure).options(
        selectinload(Measure.executions), selectinload(Measure.evidence), selectinload(Measure.deadline_changes))
        .order_by(Measure.section_code, Measure.number))
    measures, overdue_by_unit, flags = [], {}, []
    for m in rows:
        ex = _execution_dict(next((e for e in m.executions if e.period == period), None))
        risk = risks.get(m.risk_id) if m.risk_id else None
        if risk:
            risk["measures"].append(m.id)
        state = rules.portal_state(ex["status"], m.deadline_type, m.deadline_date, period_end)
        item = {
            "id": m.id, "section": m.section_code, "section_title": sections[m.section_code].title,
            "number": m.number, "content": m.content, "risk_id": m.risk_id, "risk_name": risk["name"] if risk else "",
            "unit_id": m.unit_id, "unit_name": units.get(m.unit_id, ""), "co_units": m.co_units or [],
            "co_unit_names": [units.get(u, u) for u in (m.co_units or [])], "executor_id": m.executor_id,
            "executor_position": positions.get(m.executor_id, ""),
            "deadline_text": m.deadline_text, "deadline_type": m.deadline_type, "deadline_date": m.deadline_date,
            "internal_deadline": m.deadline_changes[-1].new_date if m.deadline_changes else m.deadline_date,
            "indicator_name": m.indicator_name, "indicator_unit": m.indicator_unit,
            "indicator_target": m.indicator_target, "required_evidence": m.required_evidence,
            "resources": m.resources, "period": period, **ex,
            "evidence": [{"id": e.id, "type": e.type, "name": e.name, "doc_date": e.doc_date, "link": e.link,
                          "uploaded_at": e.uploaded_at, "uploaded_by": e.uploaded_by_id, "sha256": e.sha256,
                          "has_file": bool(e.stored_name), "original_name": e.original_name, "size": e.size}
                         for e in m.evidence],
            "postponements": [{"decision_date": c.decision_date, "old_date": c.old_date, "new_date": c.new_date,
                               "reason": c.reason, "approved_by": c.approved_by_id} for c in m.deadline_changes],
            "portal_state": state,
            "portal_actual_date": rules.portal_actual_date(ex["status"], m.deadline_type, ex["actual_date"], period_end),
            "portal_description": rules.portal_description(state, ex["result_text"]),
        }
        item["flags"] = rules.measure_flags({
            "id": m.id, "section": m.section_code, "content": m.content, "deadline_type": m.deadline_type,
            "deadline_date": m.deadline_date, "indicator_target": m.indicator_target,
            "indicator_unit": m.indicator_unit, "status": ex["status"], "actual_date": ex["actual_date"],
            "result_text": ex["result_text"], "indicator_fact": ex["indicator_fact"],
            "evidence_dates": [e.doc_date for e in m.evidence],
            "risk": {"id": risk["id"], "base": risk["base"], "current": risk["current"], "target": risk["target"]}
            if risk else None,
            "postponements": len(m.deadline_changes),
        }, period_end)
        for code, why in item["flags"]:
            flags.append({"code": code, "object": "zakhid", "id": m.id, "title": rules.FLAG_BY_CODE[code].title,
                          "explanation": why, "unit_id": m.unit_id, "unit_name": item["unit_name"]})
            if code == "RF1":
                overdue_by_unit.setdefault(m.unit_id, []).append(m.id)
        measures.append(item)

    for unit_id, code, why in rules.unit_flags(overdue_by_unit):
        flags.append({"code": code, "object": "pidrozdil", "id": unit_id, "title": rules.FLAG_BY_CODE[code].title,
                      "explanation": why, "unit_id": unit_id, "unit_name": units.get(unit_id, "")})
    for r in risks.values():
        r["flags"] = rules.risk_flags(r["id"], r["level"], len(r["measures"]))
        for code, why in r["flags"]:
            flags.append({"code": code, "object": "ryzyk", "id": r["id"], "title": rules.FLAG_BY_CODE[code].title,
                          "explanation": why, "unit_id": r["owner_unit_id"], "unit_name": r["owner_unit"]})

    program = s.scalars(select(Program)).first()
    return {
        "period": period, "period_start": period_start, "period_end": period_end,
        "program": {"id": program.id, "name": program.name, "organ": program.organ,
                    "period_start": program.period_start, "period_end": program.period_end,
                    "approved_by": program.approved_by, "nazk_status": program.nazk_status,
                    "restricted": program.restricted, "authorized_unit": units.get(program.authorized_unit_id, ""),
                    "goals": program.goals, "note": program.note} if program else None,
        "sections": [{"code": x.code, "number": x.number, "title": x.title}
                     for x in sorted(sections.values(), key=lambda x: x.number)],
        "units": units, "measures": measures, "risks": list(risks.values()), "flags": flags,
    }


def portal_report(snap: dict) -> list[dict]:
    """Звіт за півріччя у структурі Порталу доброчесності НАЗК — ті самі поля, що в еталонному звіті набору."""
    codes: dict[str, list[str]] = {}
    for f in snap["flags"]:
        if f["object"] == "zakhid":
            codes.setdefault(f["id"], []).append(f["code"])
    return [{
        "rozdil_portal": m["section_title"],
        "nomer": m["number"],
        "zakhid_id": m["id"],
        "opys_zakhodu": m["content"],
        "naimenuvannia_pidrozdilu": m["unit_name"],
        "zaplanovanyi_strok": m["deadline_text"],
        "faktychnyi_strok_vykonannia": m["portal_actual_date"].isoformat() if m["portal_actual_date"] else "",
        "stan_vykonannia": m["portal_state"],
        "opys_rezultatu_abo_prychyn": m["portal_description"],
        "pidtverdni_materialy": "; ".join(e["name"] for e in m["evidence"]),
        "sluzhbove_sygnaly_pered_perenesenniam": ", ".join(codes.get(m["id"], [])),
    } for m in snap["measures"]]
