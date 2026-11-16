"""Журнал дій: хто, коли, що і з якого значення на яке змінив; з якої адреси й пристрою.
Записи лише додаються — маршрутів для зміни чи видалення немає."""
import re
from datetime import datetime

from fastapi import Request

from ..config import TRUST_PROXY
from ..db import session
from ..models import JournalEntry
from ..utils import now_utc


def device_from_user_agent(ua: str) -> str:
    if not ua:
        return ""
    os_name = next((name for pattern, name in [
        (r"Windows", "Windows"), (r"Android", "Android"), (r"iPhone|iPad", "iOS"),
        (r"Mac OS X|Macintosh", "macOS"), (r"Linux", "Linux")] if re.search(pattern, ua)), "інша ОС")
    browser = next((name for pattern, name in [
        (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/", "Firefox"), (r"Chrome/", "Chrome"),
        (r"Safari/", "Safari"), (r"python|httpx|curl|testclient", "скрипт")] if re.search(pattern, ua, re.I)),
        "інший браузер")
    return f"{os_name} · {browser}"


def client_info(request: Request | None) -> tuple[str, str]:
    if request is None:
        return "", ""
    ip = request.client.host if request.client else ""
    if TRUST_PROXY and request.headers.get("x-forwarded-for"):
        ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    return ip, device_from_user_agent(request.headers.get("user-agent", ""))


def log(user_id: str | None, action: str, obj: str, obj_id: str, field: str = "", old="", new="",
        request: Request | None = None, at: datetime | None = None, commit: bool = False) -> None:
    ip, device = client_info(request)
    s = session()
    s.add(JournalEntry(at=at or now_utc(), user_id=user_id, action=action, object=obj, object_id=str(obj_id),
                       field=field, old_value="" if old is None else str(old),
                       new_value="" if new is None else str(new), ip=ip, device=device))
    if commit:
        s.commit()
