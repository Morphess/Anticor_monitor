"""API виконання заходів: VYK заповнює, KOORD погоджує, MAIN_KOORD читає.

Правила видимості узгоджені з program_departments/measure_assignments.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.execution import Execution
from app.models.program_workflow import MeasureAssignment
from app.models.user import User
from app.schemas.execution import (
    ExecutionApprovalUpdate,
    ExecutionCreate,
    ExecutionRead,
    ExecutionStatus,
    ExecutionUpdate,
)
from app.services.execution_services import (
    ExecutionAlreadyExistsError,
    ExecutionNotFoundError,
    ExecutionService,
    MeasureNotFoundError,
)
from app.services.measure_access import (
    require_department_coordinator,
    require_execution_actor,
    require_executor,
    require_visible_measure,
    visible_measure_ids,
)
from app.services.program_workflow_services import (
    ProgramWorkflowService,
    WorkflowError,
)

router = APIRouter(prefix="/executions", tags=["Executions"])


def get_service(
    db: Session = Depends(get_db),
) -> ExecutionService:
    return ExecutionService(db)


def _forbid_managed_fields(data, *, create: bool) -> None:
    """Автор, час і погодження не змінюються звичайним POST/PATCH."""
    supplied = data.model_fields_set

    if supplied & {"submitted_by_user_id", "submitted_at"}:
        raise HTTPException(
            status_code=422,
            detail="Автор та дата подання визначаються сервером",
        )

    if create:
        if getattr(data, "approved_by_coordinator", False):
            raise HTTPException(
                status_code=403,
                detail="Виконавець не може погодити свій результат",
            )

    elif "approved_by_coordinator" in supplied:
        raise HTTPException(
            status_code=403,
            detail="Погодження змінює лише KOORD через /approval",
        )


def _report(
    db: Session,
    measure_id: str,
    period: str,
) -> Execution:
    record = db.get(Execution, (measure_id, period))

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Виконання за цей період не знайдено",
        )

    return record


# CREATE — лише VYK
@router.post(
    "/",
    response_model=ExecutionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Подати виконання призначеного заходу",
    description=(
        "Тільки VYK, якому захід призначений через "
        "measure_assignments. Автор береться з JWT, "
        "погодження встановлює лише KOORD."
    ),
)
def create_execution(
    data: ExecutionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_executor),
    service: ExecutionService = Depends(get_service),
):
    require_visible_measure(db, actor, data.measure_id)
    _forbid_managed_fields(data, create=True)

    try:
        service.create(data)

        record = _report(
            db,
            data.measure_id,
            data.period,
        )

        record.submitted_by_user_id = actor.id
        record.submitted_at = datetime.now(timezone.utc)
        record.approved_by_coordinator = False

        db.commit()
        db.refresh(record)

        return record

    except MeasureNotFoundError as exc:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ExecutionAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception:
        db.rollback()
        raise


# READ — список доступних виконань
@router.get(
    "/",
    response_model=list[ExecutionRead],
    summary="Переглянути доступні виконання",
)
def list_executions(
    measure_id: str | None = None,
    period: str | None = None,
    status_filter: ExecutionStatus | None = Query(
        default=None,
        alias="status",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
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

    stmt = select(Execution).where(Execution.measure_id.in_(ids))

    if period is not None:
        stmt = stmt.where(Execution.period == period)

    if status_filter is not None:
        stmt = stmt.where(Execution.status == status_filter)

    stmt = (
        stmt.order_by(
            Execution.measure_id,
            Execution.period,
        )
        .offset(offset)
        .limit(limit)
    )

    return list(db.scalars(stmt))


# READ — виконання конкретного заходу
@router.get(
    "/{measure_id}/{period}",
    response_model=ExecutionRead,
    summary="Переглянути виконання заходу за період",
)
def get_execution(
    measure_id: str,
    period: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
):
    require_visible_measure(db, actor, measure_id)

    return _report(db, measure_id, period)


# UPDATE — лише автор VYK до погодження
@router.patch(
    "/{measure_id}/{period}",
    response_model=ExecutionRead,
    summary="Редагувати власне виконання до погодження",
)
def update_execution(
    measure_id: str,
    period: str,
    data: ExecutionUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_executor),
    service: ExecutionService = Depends(get_service),
):
    require_visible_measure(db, actor, measure_id)

    record = _report(db, measure_id, period)

    if record.approved_by_coordinator:
        raise HTTPException(
            status_code=409,
            detail="Погоджене виконання редагувати не можна",
        )

    if record.submitted_by_user_id != actor.id:
        raise HTTPException(
            status_code=403,
            detail="Редагувати може лише автор виконання",
        )

    _forbid_managed_fields(data, create=False)

    try:
        service.update(measure_id, period, data)
        return _report(db, measure_id, period)

    except ExecutionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# APPROVAL — лише KOORD
@router.patch(
    "/{measure_id}/{period}/approval",
    response_model=ExecutionRead,
    summary="Погодити або відкликати погодження виконання",
)
def update_execution_approval(
    measure_id: str,
    period: str,
    data: ExecutionApprovalUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_department_coordinator),
    service: ExecutionService = Depends(get_service),
):
    measure = require_visible_measure(
        db,
        actor,
        measure_id,
    )

    execution = _report(db, measure.id, period)

    if actor.department_id is None or execution.submitted_by_user_id is None:
        raise HTTPException(
            status_code=403,
            detail=("Немає визначеного автора або " "підрозділу координатора"),
        )

    assignment = db.get(
        MeasureAssignment,
        (measure_id, execution.submitted_by_user_id),
    )

    if assignment is None:
        raise HTTPException(
            status_code=403,
            detail="Автор виконання не має чинного призначення",
        )

    try:
        in_branch = ProgramWorkflowService(db).tree.is_within(
            assignment.department_id,
            actor.department_id,
        )

    except WorkflowError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    if not in_branch:
        raise HTTPException(
            status_code=403,
            detail="Виконавець поза ієрархією координатора",
        )

    try:
        return service.update_approval(
            measure_id=measure_id,
            period=period,
            approved=data.approved_by_coordinator,
        )

    except ExecutionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# DELETE — заборонено
@router.delete(
    "/{measure_id}/{period}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалення виконання заборонене",
)
def delete_execution(
    measure_id: str,
    period: str,
    actor: User = Depends(require_execution_actor),
) -> None:
    raise HTTPException(
        status_code=403,
        detail="Видалення виконань заборонено",
    )
