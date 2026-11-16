"""Логіка сторінок виконавця й координатора.

Поки моделей і таблиць немає, дані беруться з демо-файлу app/demo/monitor_demo.json
(синтетичний набір організаторів) і зберігаються в пам'яті процесу: після перезапуску
сервера все повертається до початкового стану. Коли з'являться моделі — замінити
функції _orders(), _executor(), _programs() читанням з бази, решта логіки не зміниться.
"""
import copy
import json
from pathlib import Path
from threading import Lock

DEMO_FILE = Path(__file__).resolve().parents[1] / "demo" / "monitor_demo.json"

STATUSES = {
    "done": "Виконано",
    "review": "На розгляді",
    "rework": "На доопрацюванні",
    "not": "Не виконано",
}

_lock = Lock()
_data: dict | None = None


def _load() -> dict:
    global _data
    if _data is None:
        _data = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    return _data


def reset() -> None:
    """Повернути демо-дані до початкового стану (для тестів)."""
    global _data
    with _lock:
        _data = None


def _orders() -> dict:
    return _load()["orders"]


def _executor() -> dict:
    return _load()["executor"]


def _programs() -> list[dict]:
    return _load()["programs"]


# ---------- Виконавець ----------
def executor_page() -> dict:
    """Дані для сторінки виконавця: назва підрозділу і рядки таблиці."""
    ex = _executor()
    rows = []
    for m in ex["measures"]:
        order = _orders()[m["order"]]
        rows.append({
            "id": m["id"],
            "order_title": order["title"],
            "organ": order["organ"],
            "start": m["start"],
            "end": m["end"],
            "entered": m["entered"] or "",
            "status": "виконано" if m["entered"] else m["status"],
            "goal": m["goal"],
            "indicator": m["indicator"],
            "note": m["note"],
        })
    return {"unit": ex["unit"], "rows": rows}


def check_order(measure_id: str, number: str) -> dict:
    """Перевірка номера наказу, який увів виконавець.

    Успіх — наказ є в базі, це саме той наказ, що закріплений за заходом, і ним ще
    не підтверджено інший захід. Тоді захід вважається виконаним.
    """
    number = (number or "").replace("№", "").strip()
    with _lock:
        measure = next((m for m in _executor()["measures"] if m["id"] == measure_id), None)
        if measure is None:
            return {"ok": False, "message": "Захід не знайдено"}
        if not number:
            return {"ok": False, "message": "Введіть номер наказу"}
        order = _orders().get(number)
        if order is None:
            return {"ok": False, "message": f"Помилка: наказу № {number} немає в реєстрі"}
        if order["used_by"] and order["used_by"] != measure_id:
            return {"ok": False, "message": f"Помилка: наказ № {number} уже використано для іншого заходу"}
        if number != measure["order"]:
            return {"ok": False, "message": f"Помилка: № {number} — це інший наказ («{order['title']}»)"}
        order["used_by"] = measure_id
        measure["entered"] = number
        return {"ok": True, "message": "Успіх", "status": "виконано"}


# ---------- Координатор ----------
def _item_count(item: dict) -> tuple[int, int]:
    return sum(1 for u in item["units"] if u["st"] == "done"), len(item["units"])


def _section_count(section: dict) -> tuple[int, int]:
    done = total = 0
    for item in section["items"]:
        d, t = _item_count(item)
        done, total = done + d, total + t
    return done, total


def _program_count(program: dict) -> tuple[int, int]:
    if program.get("archive"):
        return program["archive"]["done"], program["archive"]["total"]
    done = total = 0
    for section in program["sections"]:
        d, t = _section_count(section)
        done, total = done + d, total + t
    return done, total


def coordinator_page(query: str = "") -> dict:
    """Список програм з рахунком «скільки виконано» по органах. query — пошук за назвою або роком."""
    q = (query or "").strip().lower()
    programs = []
    for p in _programs():
        if q and q not in p["name"].lower() and q not in p["start"] and q not in p["end"]:
            continue
        done, total = _program_count(p)
        programs.append({**p, "done": done, "total": total})
    return {"unit": _load()["coordinator_unit"], "programs": programs, "statuses": STATUSES}


def set_unit_status(program_id: str, item_n: str, unit_index: int, status: str) -> dict:
    """Координатор змінює статус органу в підпункті. Повертає нові рахунки підпункту, розділу й програми."""
    if status not in STATUSES:
        raise ValueError("Невідомий статус")
    with _lock:
        program = next((p for p in _programs() if p["id"] == program_id), None)
        if program is None:
            raise LookupError("Програму не знайдено")
        for section in program["sections"]:
            for item in section["items"]:
                if item["n"] == item_n:
                    if not 0 <= unit_index < len(item["units"]):
                        raise LookupError("Орган не знайдено")
                    item["units"][unit_index]["st"] = status
                    i_done, i_total = _item_count(item)
                    s_done, s_total = _section_count(section)
                    p_done, p_total = _program_count(program)
                    return {
                        "status": status,
                        "label": STATUSES[status],
                        "item": {"done": i_done, "total": i_total},
                        "section": {"done": s_done, "total": s_total},
                        "program": {"done": p_done, "total": p_total},
                    }
        raise LookupError("Підпункт не знайдено")


def snapshot() -> dict:
    """Копія поточних даних (для відладки)."""
    return copy.deepcopy(_load())
