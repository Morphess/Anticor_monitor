"""Маршрути Jinja2-інтерфейсу Anticor Monitor.

Запуск FastAPI з кореня backend/: uvicorn app.main:app --reload.
frontend/ лежить поруч із backend/ у корені репозиторію.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = ROOT / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

router = APIRouter(tags=["Web UI"])


@router.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/login", status_code=302)


def page(request: Request, template: str):
    return templates.TemplateResponse(request, template)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login(request: Request):
    return page(request, "login.html")


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin(request: Request):
    return page(request, "admin.html")


@router.get("/main-coordinator", response_class=HTMLResponse, include_in_schema=False)
def main_coordinator(request: Request):
    return page(request, "main_coordinator.html")


@router.get("/coordinator", response_class=HTMLResponse, include_in_schema=False)
def coordinator(request: Request):
    return page(request, "coordinator.html")


@router.get("/executor", response_class=HTMLResponse, include_in_schema=False)
def executor(request: Request):
    return page(request, "executor.html")


@router.get("/manager", response_class=HTMLResponse, include_in_schema=False)
def manager(request: Request):
    return page(request, "manager.html")
