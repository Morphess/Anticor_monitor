"""HTML-сторінки кабінетів.

Сторінки віддаються без перевірки токена: це лише оболонка. Дані підвантажуються
скриптами через /api/..., де права перевіряє сервер.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)

# Адреса сторінки -> шаблон кабінету.
PAGES = {
    "/login": "login.html",
    "/executor": "executor.html",
    "/coordinator": "coordinator.html",
    "/manager": "manager.html",
    "/analyst": "analyst.html",
    "/admin": "admin.html",
}


def _page(template: str):
    def handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, template)

    return handler


for _path, _template in PAGES.items():
    router.add_api_route(
        _path, _page(_template), methods=["GET"], response_class=HTMLResponse
    )


@router.get("/app")
def app_entry() -> RedirectResponse:
    """Точка входу для користувача: сторінка входу."""
    return RedirectResponse("/login", status_code=303)
