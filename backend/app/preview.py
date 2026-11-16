"""Standalone local preview for the monitor UI (no DB/API required)."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services import monitor_service

app = FastAPI(title="Anticor monitor UI preview", docs_url=None, redoc_url=None)
ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(ROOT / "frontend" / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "frontend" / "static")), name="static")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "coordinator.html", monitor_service.coordinator_page())


@app.get("/coordinator")
def coordinator(request: Request):
    return templates.TemplateResponse(request, "coordinator.html", monitor_service.coordinator_page())


@app.get("/executor")
def executor(request: Request):
    return templates.TemplateResponse(request, "executor.html", monitor_service.executor_page())
