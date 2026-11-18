"""Risk Flags лише для адміністратора; без зміни стану бази."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db
from app.repositories.risk_flag_repository import RiskFlagRepository
from app.schemas.risk_flags import RiskFlagRead
from app.services.risk_flag_services import detect_risk_flags, period_bounds


router = APIRouter(
    prefix="/risk-flags",
    tags=["Risk Flags"],
    dependencies=[Depends(require_admin)],
)


@router.get("/", response_model=list[RiskFlagRead])
def list_risk_flags(
    period: str = Query(default="2026-H1", pattern=r"^\d{4}-H[12]$"),
    as_of: date = Query(..., description="Дата зрізу, наприклад 2026-07-06"),
    code: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        _, end = period_bounds(period)
        if as_of < end:
            raise ValueError("Дата зрізу не може бути раніше кінця періоду")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    snapshot = RiskFlagRepository(db).snapshot(period=period, period_end=end, as_of=as_of)
    flags = detect_risk_flags(period=period, as_of=as_of, **snapshot)
    return [flag for flag in flags if code is None or flag.code == code]
