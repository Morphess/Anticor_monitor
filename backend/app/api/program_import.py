"""Окрема ручка завантаження JSON-файлу антикорупційної програми."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.program_import import ProgramImportPayload, ProgramImportResult
from app.services.program_import_service import (
    ProgramImportConflict,
    ProgramImportInvalidReference,
    ProgramImportService,
)

router = APIRouter(prefix="/program-import", tags=["Program Import"])
MAX_JSON_SIZE = 5 * 1024 * 1024  # 5 MiB


@router.post("/", response_model=ProgramImportResult, status_code=status.HTTP_201_CREATED)
async def upload_program_json(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ProgramImportResult:
    """Приймає multipart/form-data, ключ file, з .json у UTF-8."""
    # `admin` перевіряється FastAPI до виклику функції;
    # `get_current_user` також задає автора для SQLAlchemy audit.
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Потрібен файл із розширенням .json")

    try:
        content = await file.read(MAX_JSON_SIZE + 1)
    finally:
        await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="JSON-файл порожній")
    if len(content) > MAX_JSON_SIZE:
        raise HTTPException(status_code=413, detail="Максимальний розмір JSON — 5 МіБ")

    try:
        payload = ProgramImportPayload.model_validate_json(content)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False, include_input=False),
        ) from exc

    try:
        return ProgramImportService(db).import_program(payload)
    except ProgramImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProgramImportInvalidReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
