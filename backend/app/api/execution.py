"""API підтвердних матеріалів: VYK додає, KOORD/MAIN_KOORD переглядають.

Метадані документа, не завантаження двійкового файлу.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.evidence import Evidence
from app.models.execution import Execution
from app.models.user import User
from app.schemas.evidences import EvidenceCreate, EvidenceRead, EvidenceUpdate
from app.services.evidence_services import EvidenceError, EvidenceService
from app.services.measure_access import (
    require_execution_actor,
    require_executor,
    require_visible_measure,
    visible_measure_ids,
)

router = APIRouter(prefix="/evidences", tags=["Evidences"])


def _check_not_approved(db: Session, measure_id: str) -> None:
    """Evidence не має period, тому блокуємо зміни, якщо є БУДЬ-ЯКЕ погодження."""
    is_approved = db.scalar(
        select(Execution.measure_id)
        .where(
            Execution.measure_id == measure_id,
            Execution.approved_by_coordinator.is_(True),
        )
        .limit(1)
    )
    if is_approved is not None:
        raise HTTPException(
            status_code=409,
            detail="Для заходу є погоджене виконання. Змінювати підтвердження заборонено",
        )


@router.post(
    "/",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Додати підтвердний документ до свого заходу",
    description="Тільки VYK із чинним призначенням. Після погодження виконання "
    "додавання документів блокується.",
)
def create_evidence(
    data: EvidenceCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_executor),
):
    require_visible_measure(db, actor, data.measure_id)
    _check_not_approved(db, data.measure_id)
    try:
        return EvidenceService(db).create_evidence(data)
    except EvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/",
    response_model=list[EvidenceRead],
    summary="Переглянути доступні підтвердні документи",
    description="MAIN_KOORD — свої програми; KOORD — доступні заходи; VYK — "
    "призначені заходи. Перевірка доступу відбувається до пагінації.",
)
def list_evidences(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    measure_id: str | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
):
    if measure_id is not None:
        require_visible_measure(db, actor, measure_id)
        ids = {measure_id}
    else:
        ids = visible_measure_ids(db, actor)
    if not ids:
        return []
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.measure_id.in_(ids))
            .order_by(Evidence.id)
            .offset(skip)
            .limit(limit)
        )
    )


@router.get(
    "/{evidence_id}",
    response_model=EvidenceRead,
    summary="Переглянути підтвердний документ",
)
def get_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
):
    try:
        evidence = EvidenceService(db).get_evidence(evidence_id)
    except EvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    require_visible_measure(db, actor, evidence.measure_id)
    return evidence


@router.patch(
    "/{evidence_id}",
    response_model=EvidenceRead,
    summary="Змінити підтвердження свого заходу до погодження",
)
def update_evidence(
    evidence_id: str,
    data: EvidenceUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_executor),
):
    service = EvidenceService(db)
    try:
        evidence = service.get_evidence(evidence_id)
    except EvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    require_visible_measure(db, actor, evidence.measure_id)
    _check_not_approved(db, evidence.measure_id)
    if data.measure_id is not None and data.measure_id != evidence.measure_id:
        require_visible_measure(db, actor, data.measure_id)
        _check_not_approved(db, data.measure_id)
    try:
        return service.update_evidence(evidence_id, data)
    except EvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.delete(
    "/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити підтвердження свого заходу до погодження",
)
def delete_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_executor),
):
    service = EvidenceService(db)
    try:
        evidence = service.get_evidence(evidence_id)
    except EvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    require_visible_measure(db, actor, evidence.measure_id)
    _check_not_approved(db, evidence.measure_id)
    try:
        service.delete_evidence(evidence_id)
    except EvidenceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
