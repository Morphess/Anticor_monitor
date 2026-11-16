from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.services import monitor_service

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "frontend" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)


@router.get("/executor")
def executor_page(request: Request):
    return templates.TemplateResponse(request, "executor.html", monitor_service.executor_page())


@router.get("/coordinator")
def coordinator_page(request: Request):
    return templates.TemplateResponse(request, "coordinator.html", monitor_service.coordinator_page())
