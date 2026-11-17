from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.schemas.programs import (
    ProgramCreate,
    ProgramRead,
    ProgramUpdate,
)
from app.services.program_services import ProgramService


router = APIRouter(
    prefix="/programs",
    tags=["Programs"],
)


# Отримати список усіх програм.
@router.get(
    "",
    response_model=list[ProgramRead],
)
def get_programs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = ProgramService(db)

    return service.get_all(
        skip=skip,
        limit=limit,
    )


# Отримати програму за кодом.
@router.get(
    "/{program_id}",
    response_model=ProgramRead,
)
def get_program(
    program_id: str,
    db: Session = Depends(get_db),
):
    service = ProgramService(db)

    return service.get_by_id(program_id)


# Створити нову антикорупційну програму.
@router.post(
    "",
    response_model=ProgramRead,
    status_code=status.HTTP_201_CREATED,
)
def create_program(
    data: ProgramCreate,
    db: Session = Depends(get_db),
):
    service = ProgramService(db)

    return service.create(data)


# Частково оновити програму.
@router.patch(
    "/{program_id}",
    response_model=ProgramRead,
)
def update_program(
    program_id: str,
    data: ProgramUpdate,
    db: Session = Depends(get_db),
):
    service = ProgramService(db)

    return service.update(
        program_id=program_id,
        data=data,
    )


# Видалити програму.
@router.delete(
    "/{program_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_program(
    program_id: str,
    db: Session = Depends(get_db),
):
    service = ProgramService(db)

    service.delete(program_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
