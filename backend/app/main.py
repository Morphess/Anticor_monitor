from pathlib import Path
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.db_connection import get_db, engine

from app.core.config import settings
from app.core.audit import enable_audit

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.coordinator_users import router as coordinator_users_router
from app.api.programs import router as programs_router
from app.api.departments import router as departments_router
from app.api.sections import router as sections_router
from app.api.measures import router as measures_router
from app.api.risks import router as risks_router
from app.api.risk_assessments import router as risk_assessments_router
from app.api.execution import router as execution_router
from app.api.deadline_changes import router as deadline_changes_router
from app.api.reports import router as reports_router
from app.api.action_logs import router as action_logs_router
from app.api.orders import router as orders_router
from app.api.risk_flags import router as risk_flags_router
from app.api.program_import import router as program_import_router
from app.api.program_workflow import router as program_workflow_router
from app.api.dashboard import router as dashboard_router
from app.api.deadline_reminders import router as deadline_reminders_router
from app.api.order_change_alerts import router as order_change_alerts_router
from app.api.management_dashboard import router as management_dashboard_router
from app.web.frontend_pages import FRONTEND_DIR, router as frontend_router

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parents[2]

FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Anticor Monitor запускається...")

    try:
        yield
    finally:
        engine.dispose()
        logger.info("Anticor Monitor завершив роботу.")


enable_audit()

app = FastAPI(
    title="Anticor Monitor API",
    description="API системи моніторингу корупційних ризиків",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(coordinator_users_router, prefix="/api")
app.include_router(programs_router, prefix="/api")
app.include_router(sections_router, prefix="/api")
app.include_router(measures_router, prefix="/api")
app.include_router(risks_router, prefix="/api")
app.include_router(risk_assessments_router, prefix="/api")
app.include_router(execution_router, prefix="/api")
app.include_router(deadline_changes_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(action_logs_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(risk_flags_router, prefix="/api")
app.include_router(departments_router, prefix="/api")
app.include_router(program_import_router, prefix="/api")
app.include_router(program_workflow_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(deadline_reminders_router, prefix="/api")
app.include_router(order_change_alerts_router, prefix="/api")
app.include_router(management_dashboard_router, prefix="/api")
app.include_router(frontend_router)


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


@app.get("/", tags=["System"])
def read_root():
    return {
        "app": "Anticor Monitor",
        "status": "running",
    }


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "message": "FastAPI працює",
    }


@app.get("/db", tags=["System"])
def database_health_check(
    db: Session = Depends(get_db),
):
    try:
        result = db.execute(text("SELECT 1")).scalar_one()

        return {
            "status": "connected",
            "database": "PostgreSQL",
            "result": result,
        }

    except SQLAlchemyError as error:
        logger.exception("Помилка підключення до PostgreSQL")

        raise HTTPException(
            status_code=503,
            detail="Не вдалося підключитися до PostgreSQL",
        ) from error
