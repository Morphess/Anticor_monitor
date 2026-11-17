from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

# Сторінки — оболонки: дані JS бере з /api з JWT-токеном,
# тож перевірка прав лишається на боці API.
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/executor")
def executor_page(request: Request):
    return templates.TemplateResponse(request, "executor.html")


@router.get("/admin")
def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html")


@router.get("/coordinator")
def coordinator_page(request: Request):
    return templates.TemplateResponse(request, "coordinator.html")


@router.get("/analyst")
def analyst_page(request: Request):
    return templates.TemplateResponse(request, "analyst.html")


@router.get("/manager")
def manager_page(request: Request):
    return templates.TemplateResponse(request, "manager.html")
