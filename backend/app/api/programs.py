"""CRUD програм: створює MAIN_KOORD; читання — за доступом program-routing."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.main_coordinator import require_main_coordinator
from app.database.db_connection import get_db
from app.models.program import Program
from app.models.user import User
from app.schemas.programs import ProgramCreate, ProgramRead, ProgramUpdate
from app.services.program_services import ProgramService
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError

router = APIRouter(prefix="/programs", tags=["Programs"])


def _check_owner(db: Session, program_id: str, actor: User) -> Program:
    """MAIN_KOORD редагує лише програму, яку сам створив."""
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Програму не знайдено")
    if program.created_by_user_id != actor.id:
        raise HTTPException(status_code=403, detail="Можна змінювати лише власні програми")
    return program


@router.get(
    "", response_model=list[ProgramRead],
    summary="Мої доступні програми",
    description="MAIN_KOORD бачить власні програми, KOORD — передані підрозділу, VYK — програми із персональними призначеннями, ADMIN — всі.",
)
def get_programs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    allowed_ids = [p["id"] for p in ProgramWorkflowService(db).my_programs(actor)]
    if not allowed_ids:
        return []
    stmt = (
        select(Program)
        .where(Program.id.in_(allowed_ids))
        .order_by(Program.id)
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt))


@router.get("/{program_id}", response_model=ProgramRead, summary="Переглянути доступну програму")
def get_program(
    program_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    try:
        return ProgramWorkflowService(db).visible_program(program_id, actor)
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post(
    "", response_model=ProgramRead, status_code=status.HTTP_201_CREATED,
    summary="Створити програму (MAIN_KOORD)",
    description="Створює програму та атомарно записує created_by_user_id із JWT. Інший користувач не може підмінити власника.",
)
def create_program(
    data: ProgramCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    # Тут ORM створюється безпосередньо, щоб власник зберігся тим самим commit,
    # а не окремим UPDATE після ProgramService.create().
    fields = data.model_dump(exclude={"created_by_user_id"})
    program = Program(**fields, created_by_user_id=actor.id)
    try:
        db.add(program)
        db.commit()
        db.refresh(program)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Конфлікт ID програми або зовнішнього ключа") from exc
    return program


@router.patch("/{program_id}", response_model=ProgramRead, summary="Змінити власну програму (MAIN_KOORD)")
def update_program(
    program_id: str,
    data: ProgramUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    _check_owner(db, program_id, actor)
    changes = data.model_dump(exclude_unset=True)
    if "created_by_user_id" in changes:
        raise HTTPException(status_code=422, detail="Власника програми змінювати не можна")
    return ProgramService(db).update(program_id=program_id, data=data)


@router.delete("/{program_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Видалити власну програму (MAIN_KOORD)")
def delete_program(
    program_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_main_coordinator),
):
    _check_owner(db, program_id, actor)
    ProgramService(db).delete(program_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
