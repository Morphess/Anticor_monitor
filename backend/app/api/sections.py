from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.core.dependencies import require_admin

from app.schemas.section import (
    SectionCreate,
    SectionRead,
    SectionUpdate,
)

from app.services.section_services import (
    SectionService,
    SectionNotFoundError,
    SectionAlreadyExistsError,
    InvalidSectionDataError,
)


router = APIRouter(
    prefix="/sections",
    tags=["Sections"],
    dependencies=[Depends(require_admin)],
)


# GET — УСІ РОЗДІЛИ
@router.get(
    "/",
    response_model=list[SectionRead],
)
def list_sections(
    db: Session = Depends(get_db),
):
    return SectionService(db).list_sections()


# GET — ОДИН РОЗДІЛ
@router.get(
    "/{section_id}",
    response_model=SectionRead,
)
def get_section(
    section_id: str,
    db: Session = Depends(get_db),
):
    try:
        return SectionService(db).get_section(section_id)

    except SectionNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


# POST — СТВОРИТИ ВІДСУТНІЙ РОЗДІЛ
@router.post(
    "/",
    response_model=SectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_section(
    data: SectionCreate,
    db: Session = Depends(get_db),
):
    try:
        return SectionService(db).create_section(data)

    except SectionAlreadyExistsError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error

    except InvalidSectionDataError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error


# PATCH — ЗМІНИТИ НАЗВУ РОЗДІЛУ
@router.patch(
    "/{section_id}",
    response_model=SectionRead,
)
def update_section(
    section_id: str,
    data: SectionUpdate,
    db: Session = Depends(get_db),
):
    try:
        return SectionService(db).update_section(
            section_id,
            data,
        )

    except SectionNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except InvalidSectionDataError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error
