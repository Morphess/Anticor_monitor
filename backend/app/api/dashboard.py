"""API Dashboard. Дані тільки для авторизованих користувачів у межах workflow."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.dashboard import (
    DashboardSummary, DepartmentDashboard, RiskDashboard, DeadlineDashboard, MyDashboard,
)
from app.services.dashboard_services import DashboardService, DashboardError, half_year
from app.services.program_workflow_services import WorkflowError

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _coordinator(user: User = Depends(get_current_user)) -> User:
    if user.role_id not in {"MAIN_KOORD", "KOORD"}:
        raise HTTPException(status_code=403, detail="Dashboard координатора лише для MAIN_KOORD/KOORD")
    return user


def _executor(user: User = Depends(get_current_user)) -> User:
    if user.role_id != "VYK":
        raise HTTPException(status_code=403, detail="Особистий Dashboard лише для VYK")
    return user


def _params(period: str | None, as_of: date | None) -> tuple[str, date]:
    cut = as_of or date.today()
    return (period or half_year(cut), cut)


def _handle(callback):
    try:
        return callback()
    except (WorkflowError, DashboardError) as exc:
        code = exc.status_code
        detail = getattr(exc, "detail", str(exc))
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/summary", response_model=DashboardSummary)
def summary(
    program_id: str = Query(..., min_length=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    upcoming_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    actor: User = Depends(_coordinator),
):
    selected_period, cut = _params(period, as_of)
    return _handle(lambda: DashboardService(db).summary(
        program_id, actor, period=selected_period, as_of=cut, upcoming_days=upcoming_days))


@router.get("/departments", response_model=DepartmentDashboard)
def departments(
    program_id: str = Query(..., min_length=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(_coordinator),
):
    selected_period, cut = _params(period, as_of)
    return _handle(lambda: DashboardService(db).departments(
        program_id, actor, period=selected_period, as_of=cut))


@router.get("/risks", response_model=RiskDashboard)
def risks(
    program_id: str = Query(..., min_length=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(_coordinator),
):
    selected_period, cut = _params(period, as_of)
    return _handle(lambda: DashboardService(db).risks(
        program_id, actor, period=selected_period, as_of=cut))


@router.get("/deadlines", response_model=DeadlineDashboard)
def deadlines(
    program_id: str = Query(..., min_length=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    horizon_days: int = Query(default=14, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: User = Depends(_coordinator),
):
    selected_period, cut = _params(period, as_of)
    return _handle(lambda: DashboardService(db).deadlines(
        program_id, actor, period=selected_period, as_of=cut,
        horizon_days=horizon_days, limit=limit))


@router.get("/my", response_model=MyDashboard)
def my_dashboard(
    program_id: str = Query(..., min_length=1),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    horizon_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    actor: User = Depends(_executor),
):
    selected_period, cut = _params(period, as_of)
    return _handle(lambda: DashboardService(db).my(
        program_id, actor, period=selected_period, as_of=cut, horizon_days=horizon_days))
