"""Шаблони Jinja2 (frontend/templates), flash-повідомлення, фільтри."""
from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import DEMO_MODE, FRONTEND_DIR
from .services import monitor, rules
from .utils import fmt_date, fmt_dt, fmt_num, period_label

templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))
templates.env.filters.update(dt=fmt_dt, d=fmt_date, num=fmt_num, period=period_label)
templates.env.globals.update(
    STATUS_LABELS=rules.STATUS_LABELS, REVIEW_LABELS=rules.REVIEW_LABELS, ROLES=rules.ROLES,
    DEADLINE_TYPES=rules.DEADLINE_TYPES, FLAG_BY_CODE=rules.FLAG_BY_CODE, FLAG_RULES=rules.FLAG_RULES,
    DEMO_MODE=DEMO_MODE,
)


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append([kind, message])


def render(request: Request, template: str, user: dict | None = None, status_code: int = 200, **ctx):
    flashes = request.session.pop("flash", [])
    base = {"user": user, "flashes": flashes}
    try:
        base.update(current_period=monitor.current_period(), as_of=monitor.as_of_date())
    except Exception:  # сторінка помилки має відкриватися навіть без бази
        base.update(current_period="", as_of=None)
    return templates.TemplateResponse(request, template, {**base, **ctx}, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
