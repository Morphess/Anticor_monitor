"""KER-only read APIs. No POST/PATCH/DELETE routes are exposed."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.management_dashboard import (
    ManagementDeadline, ManagementMeasure, ManagementProgram,
    ManagementRecommendationsResponse, ManagementRisk, ManagementSummary,
    ManagementDepartmentProgressResponse,
)
from app.services.management_dashboard_services import (
    ManagementDashboardError, ManagementDashboardService, default_period,
)


router = APIRouter(prefix="/management", tags=["Management — KER"])


def require_department_head(user: User = Depends(get_current_user)) -> User:
    if user.role_id != "KER":
        raise HTTPException(status_code=403, detail="Цей кабінет призначений лише для KER")
    if not user.department_id:
        raise HTTPException(status_code=403, detail="Керівнику не призначено підрозділ")
    return user


def _params(period: str | None, as_of: date | None) -> tuple[str, date]:
    selected_day = as_of or date.today()
    return period or default_period(selected_day), selected_day


def _call(callback):
    try:
        return callback()
    except ManagementDashboardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/dashboard", response_model=ManagementSummary,
            summary="Огляд виконання заходів підрозділу керівника")
def dashboard(
    program_id: str | None = Query(default=None, min_length=1, max_length=50),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    upcoming_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).dashboard(
        actor, program_id=program_id, period=chosen_period,
        as_of=chosen_date, upcoming_days=upcoming_days
    ))


@router.get("/recommendations", response_model=ManagementRecommendationsResponse,
            summary="Пояснювані рекомендації: на що звернути увагу")
def recommendations(
    program_id: str | None = Query(default=None, min_length=1, max_length=50),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).recommendations(
        actor, program_id=program_id, period=chosen_period, as_of=chosen_date,
        limit=limit
    ))


@router.get("/risks", response_model=list[ManagementRisk],
            summary="Ризики підрозділу й зміни їхніх індикаторів")
def risks(
    program_id: str | None = Query(default=None, min_length=1, max_length=50),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).risks(
        actor, program_id=program_id, period=chosen_period, as_of=chosen_date
    ))


@router.get("/deadlines", response_model=list[ManagementDeadline],
            summary="Прострочені та найближчі контрольні строки")
def deadlines(
    program_id: str | None = Query(default=None, min_length=1, max_length=50),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    horizon_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).deadlines(
        actor, program_id=program_id, period=chosen_period, as_of=chosen_date,
        horizon_days=horizon_days
    ))


@router.get("/programs", response_model=list[ManagementProgram],
            summary="Програми керівника й підрозділи, на які їх координовано")
def programs(
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).programs(
        actor, period=chosen_period, as_of=chosen_date
    ))


@router.get("/measures", response_model=list[ManagementMeasure],
            summary="Заходи програм керівника зі станом виконання (лише читання)")
def measures(
    program_id: str | None = Query(default=None, min_length=1, max_length=50),
    period: str | None = Query(default=None, pattern=r"^\d{4}-H[12]$"),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).measures(
        actor, program_id=program_id, period=chosen_period, as_of=chosen_date
    ))


@router.get('/department-progress', response_model=ManagementDepartmentProgressResponse,
            summary='KER: прогрес виконавців у своєму та підпорядкованих підрозділах')
def department_progress(
    program_id: str | None = Query(default=None, min_length=1, max_length=50),
    period: str | None = Query(default=None, pattern=r'^\d{4}-H[12]$'),
    as_of: date | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_head),
):
    chosen_period, chosen_date = _params(period, as_of)
    return _call(lambda: ManagementDashboardService(db).department_progress(
        actor, program_id=program_id, period=chosen_period, as_of=chosen_date
    ))
