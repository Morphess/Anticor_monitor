"""Моніторинг і переоцінка ризиків без зміни механізму виконання наказів."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.risk_assessments import (
    AssessmentDecision, AssessmentDraftCreate, AssessmentRead,
    MeasurementCreate, MeasurementRead, TrendRead,
)
from app.services.risk_assessment_services import RiskAssessmentService, AssessmentError

router = APIRouter(prefix="/risk-assessments", tags=["Risk dynamics"])


def _call(operation):
    try:
        return operation()
    except AssessmentError as error:
        raise HTTPException(error.code, detail=error.detail) from error


@router.get("/{risk_id}/trend", response_model=TrendRead)
def risk_trend(
    risk_id: str, db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).trend(risk_id, actor))


@router.get("/{risk_id}/history", response_model=list[AssessmentRead])
def risk_history(
    risk_id: str, db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).history(risk_id, actor))


@router.post("/{risk_id}/measurements", response_model=MeasurementRead,
             status_code=status.HTTP_201_CREATED)
def create_risk_measurement(
    risk_id: str, data: MeasurementCreate,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).register_measurement(risk_id, actor, data))


@router.post("/{risk_id}/baseline", response_model=AssessmentRead,
             status_code=status.HTTP_201_CREATED)
def initialize_risk_baseline(
    risk_id: str, db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).ensure_baseline(risk_id, actor))


@router.post("/{risk_id}/drafts", response_model=AssessmentRead,
             status_code=status.HTTP_201_CREATED)
def create_reassessment_draft(
    risk_id: str, data: AssessmentDraftCreate,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).create_draft(risk_id, actor, data))


@router.post("/{risk_id}/drafts/{assessment_id}/approve", response_model=AssessmentRead)
def approve_reassessment(
    risk_id: str, assessment_id: int, data: AssessmentDecision,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).approve(risk_id, assessment_id, actor, data.reason))


@router.post("/{risk_id}/drafts/{assessment_id}/reject", response_model=AssessmentRead)
def reject_reassessment(
    risk_id: str, assessment_id: int, data: AssessmentDecision,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
):
    return _call(lambda: RiskAssessmentService(db).reject(risk_id, assessment_id, actor, data.reason))
