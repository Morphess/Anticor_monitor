"""Права на заходи: план редагує MAIN_KOORD; читання фільтрується через workflow."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.main_coordinator import require_main_coordinator
from app.database.db_connection import get_db
from app.models.measure import Measure
from app.models.program import Program
from app.models.user import User
from app.schemas.measures import MeasureCreate, MeasureRead, MeasureUpdate
from app.services.measure_services import MeasureError, MeasureService
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError

router = APIRouter(prefix="/measures", tags=["Measures"])


def _owner(db: Session, program_id: str, actor: User) -> None:
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Програму не знайдено")
    if program.created_by_user_id != actor.id:
        raise HTTPException(status_code=403, detail="Змінювати заходи може тільки власник програми MAIN_KOORD")


def _existing_measure(db: Session, measure_id: str) -> Measure:
    measure = db.get(Measure, measure_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Захід не знайдено")
    return measure


def _service_error(exc: MeasureError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _visible_ids(db: Session, program_id: str, actor: User) -> set[str]:
    try:
        rows = ProgramWorkflowService(db).program_measures(program_id, actor)
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {row["id"] for row in rows}


@router.post("/", response_model=MeasureRead, status_code=201, summary="Створити захід (MAIN_KOORD)")
def create_measure(
    data: MeasureCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    _owner(db, data.program_id, actor)
    if getattr(data, "assigned_user_id", None) is not None:
        raise HTTPException(status_code=422, detail="Виконавця призначають тільки через program-routing")
    try:
        return MeasureService(db).create_measure(data)
    except MeasureError as exc:
        raise _service_error(exc) from exc


@router.get("/", response_model=list[MeasureRead], summary="Список доступних заходів")
def list_measures(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    program_id: str | None = None,
    section_id: str | None = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    workflow = ProgramWorkflowService(db)
    if program_id:
        ids = _visible_ids(db, program_id, actor)
    else:
        ids = set()
        for item in workflow.my_programs(actor):
            ids.update(_visible_ids(db, item["id"], actor))
    if not ids:
        return []
    stmt = select(Measure).where(Measure.id.in_(ids))
    if section_id is not None:
        stmt = stmt.where(Measure.section_id == section_id)
    stmt = stmt.order_by(Measure.program_id, Measure.section_id, Measure.sequence_number).offset(skip).limit(limit)
    return list(db.scalars(stmt))


@router.get("/{measure_id}", response_model=MeasureRead, summary="Переглянути доступний захід")
def get_measure(
    measure_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    measure = _existing_measure(db, measure_id)
    if measure_id not in _visible_ids(db, measure.program_id, actor):
        raise HTTPException(status_code=403, detail="Немає доступу до цього заходу")
    try:
        return MeasureService(db).get_measure(measure_id)
    except MeasureError as exc:
        raise _service_error(exc) from exc


@router.patch("/{measure_id}", response_model=MeasureRead, summary="Редагувати захід власної програми (MAIN_KOORD)")
def update_measure(
    measure_id: str,
    data: MeasureUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    measure = _existing_measure(db, measure_id)
    _owner(db, measure.program_id, actor)
    changes = data.model_dump(exclude_unset=True)
    if "assigned_user_id" in changes or ("program_id" in changes and changes["program_id"] != measure.program_id):
        raise HTTPException(status_code=422, detail="Не можна змінювати виконавця або переносити захід в іншу програму")
    try:
        return MeasureService(db).update_measure(measure_id, data)
    except MeasureError as exc:
        raise _service_error(exc) from exc


@router.delete("/{measure_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Видалити захід власної програми (MAIN_KOORD)")
def delete_measure(
    measure_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    measure = _existing_measure(db, measure_id)
    _owner(db, measure.program_id, actor)
    try:
        MeasureService(db).delete_measure(measure_id)
    except MeasureError as exc:
        raise _service_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
