"""JSON API для інтеграції з іншими системами (лише читання). Документація: /docs

Доступ — за тією самою сесією й ролями, що й сторінки: виконавець бачить лише власні заходи.
Для міжсистемного обміну в закритому контурі сюди додається автентифікація за ключем сервісу (див. docs/architecture.md).
"""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import can_view_measure, current_user, sees_all
from ..services import monitor, rules

router = APIRouter(prefix="/api/v1", tags=["API"])


def _snap(period: str | None) -> dict:
    try:
        return monitor.snapshot(period or None)
    except Exception:
        raise HTTPException(400, "Період вказують так: 2026-H1")


def _measure(m: dict) -> dict:
    return {**m, "flags": [{"code": c, "explanation": why} for c, why in m["flags"]]}


def _risk(r: dict) -> dict:
    return {**r, "flags": [{"code": c, "explanation": why} for c, why in r["flags"]]}


@router.get("/program", summary="Паспорт програми і розділи")
def program(period: str | None = None, user: dict = Depends(current_user)):
    snap = _snap(period)
    return {"period": snap["period"], "program": snap["program"], "sections": snap["sections"],
            "units": [{"id": k, "name": v} for k, v in sorted(snap["units"].items())]}


@router.get("/measures", summary="Заходи з виконанням, підтвердженнями, станом для Порталу й сигналами")
def measures(period: str | None = None, section: str | None = None, unit: str | None = None,
             user: dict = Depends(current_user)):
    rows = [m for m in _snap(period)["measures"] if can_view_measure(user, m)
            and (not section or m["section"] == section) and (not unit or m["unit_id"] == unit)]
    return [_measure(m) for m in rows]


@router.get("/measures/{measure_id}", summary="Один захід")
def measure(measure_id: str, period: str | None = None, user: dict = Depends(current_user)):
    m = next((x for x in _snap(period)["measures"] if x["id"] == measure_id), None)
    if not m or not can_view_measure(user, m):
        raise HTTPException(404, "Захід не знайдено")
    return _measure(m)


@router.get("/risks", summary="Реєстр ризиків: рівень, індикатор, прогрес, пов'язані заходи")
def risks(period: str | None = None, user: dict = Depends(sees_all)):
    return [_risk(r) for r in _snap(period)["risks"]]


@router.get("/flags", summary="Сигнали RF1–RF7 з поясненнями")
def flags(period: str | None = None, code: str | None = None, user: dict = Depends(sees_all)):
    return [f for f in _snap(period)["flags"] if not code or f["code"] == code]


@router.get("/report", summary="Звіт за півріччя у структурі Порталу доброчесності НАЗК")
def report(period: str | None = None, user: dict = Depends(sees_all)):
    snap = _snap(period)
    return {"period": snap["period"], "rows": monitor.portal_report(snap)}


@router.get("/rules", summary="Правила, за якими формуються сигнали")
def rule_list(user: dict = Depends(current_user)):
    return [{"code": f.code, "title": f.title, "rule": f.rule, "object": f.obj} for f in rules.FLAG_RULES]
