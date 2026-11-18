"""Завантаження JSON із програмою, її розділами й заходами через Swagger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.program_import import ProgramImportPayload, ProgramImportResult
from app.services.program_import_service import (
    ProgramImportConflict,
    ProgramImportForbidden,
    ProgramImportInvalidReference,
    ProgramImportService,
)

router = APIRouter(prefix="/program-import", tags=["Program Import"])
MAX_JSON_SIZE = 5 * 1024 * 1024


@router.post(
    "/",
    response_model=ProgramImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Імпортувати програму, розділи та заходи з JSON",
    description=(
        "Приймає UTF-8 JSON через multipart/form-data (поле `file`). "
        "`KOORD` імпортує програму для свого підрозділу та стає її головним координатором. "
        "`ADMIN` може вказати `owner_coordinator_user_id` для призначення KOORD-власника. "
        "Існуючі розділи повторно використовуються. "
        "Підрозділи, ризики й користувачі мають уже існувати у БД. "
        "Розсилка програми та персональні призначення НЕ відбуваються автоматично — "
        "вони виконуються через `/api/program-routing`. "
        "При помилці весь імпорт відкочується. Повторна програма — 409."
    ),
    response_description="Результат атомарного імпорту (0 розсилок і 0 призначень)",
    responses={
        400: {"description": "Не .json або файл порожній"},
        401: {"description": "Не авторизовано"},
        403: {"description": "Невідповідна роль або спроба призначити чужого власника"},
        409: {"description": "Програма, розділ або захід конфліктують із БД"},
        413: {"description": "Розмір перевищує 5 МіБ"},
        422: {"description": "Невалідний JSON, відсутні FK або помилка структури підрозділів"},
    },
)
async def upload_program_json(
    file: UploadFile = File(..., description="JSON із ключами `program` і `sections`"),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ProgramImportResult:
    """Валідує розмір і структуру, потім передає у сервіс атомарного імпорту."""
    if actor.role_id not in {"ADMIN", "KOORD"}:
        raise HTTPException(status_code=403, detail="Імпортувати програму можуть лише ADMIN або KOORD")
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
        return ProgramImportService(db).import_program(payload, actor)
    except ProgramImportForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProgramImportConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProgramImportInvalidReference as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
