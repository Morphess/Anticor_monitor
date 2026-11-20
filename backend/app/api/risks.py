"""Independent risk registry for MAIN_KOORD within user's department.

A risk is not assigned to a program. The association exists on Measure.risk_id.
The owner department is ALWAYS derived from the authenticated user.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.main_coordinator import require_main_coordinator
from app.database.db_connection import get_db
from app.models.risk import Risk
from app.models.user import User
from app.schemas.risks import RiskCreate, RiskRead, RiskUpdate
from app.services.risk_services import RiskError, RiskService

router = APIRouter(prefix="/risks", tags=["Risks"])


def _department(actor: User) -> str:
    if not actor.department_id:
        raise HTTPException(403, detail="Головному координатору не призначено підрозділ")
    return actor.department_id


def _owned(db: Session, risk_id: str, actor: User) -> Risk:
    risk = db.get(Risk, risk_id)
    if risk is None:
        raise HTTPException(404, detail="Ризик не знайдено")
    if risk.owner_department_id != _department(actor):
        raise HTTPException(403, detail="Ризик належить іншому підрозділу")
    return risk


def _api_error(error: RiskError) -> HTTPException:
    return HTTPException(error.status_code, detail=str(error))


@router.post("/", response_model=RiskRead, status_code=status.HTTP_201_CREATED)
def create_risk(
    data: RiskCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    try:
        return RiskService(db).create_risk(data, owner_department_id=_department(actor))
    except RiskError as error:
        raise _api_error(error) from error


@router.get("/", response_model=list[RiskRead])
def list_risks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    stmt = (select(Risk)
            .where(Risk.owner_department_id == _department(actor))
            .order_by(Risk.id).offset(skip).limit(limit))
    return list(db.scalars(stmt))


@router.get("/{risk_id}", response_model=RiskRead)
def get_risk(risk_id: str, db: Session = Depends(get_db),
             actor: User = Depends(require_main_coordinator)):
    return _owned(db, risk_id, actor)


@router.patch("/{risk_id}", response_model=RiskRead)
def update_risk(risk_id: str, data: RiskUpdate,
                db: Session = Depends(get_db),
                actor: User = Depends(require_main_coordinator)):
    _owned(db, risk_id, actor)
    if {'probability_score', 'impact_score', 'score', 'level'} & data.model_fields_set:
        raise HTTPException(409, detail='Оцінка ризику змінюється лише через /risk-assessments/{risk_id}/drafts')
    try:
        return RiskService(db).update_risk(risk_id, data)
    except RiskError as error:
        raise _api_error(error) from error


@router.delete("/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(risk_id: str, db: Session = Depends(get_db),
                actor: User = Depends(require_main_coordinator)):
    _owned(db, risk_id, actor)
    try:
        RiskService(db).delete_risk(risk_id)
    except RiskError as error:
        raise _api_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
