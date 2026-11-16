"""Допоміжні функції: дати, півріччя, форматування."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)
ROMAN = {1: "І", 2: "ІІ"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def period_bounds(period: str) -> tuple[date, date]:
    """'2026-H1' -> (2026-01-01, 2026-06-30); '2026-H2' -> (2026-07-01, 2026-12-31)."""
    year, half = period.split("-H")
    year = int(year)
    return (date(year, 1, 1), date(year, 6, 30)) if half == "1" else (date(year, 7, 1), date(year, 12, 31))


def period_of(d: date) -> str:
    return f"{d.year}-H{1 if d.month <= 6 else 2}"


def period_label(period: str) -> str:
    """'2026-H1' -> 'І півріччя 2026 року'."""
    try:
        year, half = period.split("-H")
        return f"{ROMAN[int(half)]} півріччя {year} року"
    except (ValueError, KeyError):
        return period


def periods_between(start: date, end: date) -> list[str]:
    out, y, h = [], start.year, 1 if start.month <= 6 else 2
    while (y, h) <= (end.year, 1 if end.month <= 6 else 2):
        out.append(f"{y}-H{h}")
        y, h = (y, 2) if h == 1 else (y + 1, 1)
    return out


def fmt_dt(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    return str(value)


def fmt_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y")


def fmt_num(value) -> str:
    """12.0 -> '12', 12.5 -> '12,5', None -> ''."""
    if value is None or value == "":
        return ""
    f = float(value)
    return str(int(f)) if f == int(f) else f"{f:g}".replace(".", ",")


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError:
        return None
