"""HTTP API звітності: /api/executions/."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.schemas.execution import (
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

from app.schemas.execution import ExecutionApprovalUpdate

router = APIRouter(prefix="/executions", tags=["Executions"])


def get_service(db: Session = Depends(get_db)) -> ExecutionService:
    return ExecutionService(db)


@router.post("/", response_model=ExecutionRead, status_code=status.HTTP_201_CREATED)
def create_execution(
    data: ExecutionCreate,
    service: ExecutionService = Depends(get_service),
):
    try:
        return service.create(data)
    except MeasureNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ExecutionAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/", response_model=list[ExecutionRead])
def list_executions(
    measure_id: str | None = None,
    period: str | None = None,
    status_filter: ExecutionStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: ExecutionService = Depends(get_service),
):
    return service.list(
        measure_id=measure_id,
        period=period,
        status=status_filter,
        offset=offset,
        limit=limit,
    )


@router.get("/{measure_id}/{period}", response_model=ExecutionRead)
def get_execution(
    measure_id: str,
    period: str,
    service: ExecutionService = Depends(get_service),
):
    try:
        return service.get(measure_id, period)
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{measure_id}/{period}", response_model=ExecutionRead)
def update_execution(
    measure_id: str,
    period: str,
    data: ExecutionUpdate,
    service: ExecutionService = Depends(get_service),
):
    try:
        return service.update(measure_id, period, data)
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch(
    "/{measure_id}/{period}/approval",
    response_model=ExecutionRead,
    summary="Погодження звіту координатором",
)
def update_execution_approval(
    measure_id: str,
    period: str,
    data: ExecutionApprovalUpdate,
    service: ExecutionService = Depends(get_service),
):
    """Змінює стан погодження звіту."""

    try:
        return service.update_approval(
            measure_id=measure_id,
            period=period,
            approved=data.approved_by_coordinator,
        )

    except ExecutionNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@router.delete("/{measure_id}/{period}", status_code=status.HTTP_204_NO_CONTENT)
def delete_execution(
    measure_id: str,
    period: str,
    service: ExecutionService = Depends(get_service),
) -> None:
    try:
        service.delete(measure_id, period)
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
