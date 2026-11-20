"""Довідник розділів: усі операції доступні тільки MAIN_KOORD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.main_coordinator import require_main_coordinator
from app.database.db_connection import get_db
from app.schemas.section import SectionCreate, SectionRead, SectionUpdate
from app.services.section_services import (
    SectionService,
    SectionNotFoundError,
    SectionAlreadyExistsError,
    InvalidSectionDataError,
)

router = APIRouter(prefix="/sections", tags=["Sections"])


@router.get(
    "/", response_model=list[SectionRead], summary="Переглянути довідник розділів"
)
def list_sections(
    db: Session = Depends(get_db),
    _user=Depends(require_main_coordinator),
):
    return SectionService(db).list_sections()


@router.get("/{section_id}", response_model=SectionRead, summary="Отримати розділ")
def get_section(
    section_id: str,
    db: Session = Depends(get_db),
    _user=Depends(require_main_coordinator),
):
    try:
        return SectionService(db).get_section(section_id)
    except SectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/",
    response_model=SectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Створити розділ (MAIN_KOORD)",
)
def create_section(
    data: SectionCreate,
    db: Session = Depends(get_db),
    _main=Depends(require_main_coordinator),
):
    try:
        return SectionService(db).create_section(data)
    except SectionAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidSectionDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/{section_id}", response_model=SectionRead, summary="Змінити розділ (MAIN_KOORD)"
)
def update_section(
    section_id: str,
    data: SectionUpdate,
    db: Session = Depends(get_db),
    _main=Depends(require_main_coordinator),
):
    try:
        return SectionService(db).update_section(section_id, data)
    except SectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidSectionDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
