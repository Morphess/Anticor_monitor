"""Registry API: ADMIN authentication, and local-only write operations.

The private document endpoint for execution approval is in app.api.execution.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
    File,
    Form,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.core.dependencies import require_admin
from app.models.user import User
from app.schemas.orders import OrderCreate, OrderRead, OrderUpdate
from app.services.order_services import OrderError, OrderService
from app.services.order_version_services import OrderVersionService
from app.services.order_document_storage import (
    OrderDocumentStorage,
    DocumentStorageError,
)
from fastapi.responses import FileResponse
from app.schemas.order_versions import OrderVersionRead

router = APIRouter(prefix="/orders", tags=["Orders"], dependencies=[Depends(require_admin)])


@router.post(
    "/",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Створити наказ у реєстрі",
)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    try:
        return OrderService(db).create_order(data)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/", response_model=list[OrderRead], summary="Переглянути накази")
def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    return OrderService(db).list_orders(skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderRead, summary="Переглянути наказ за ID")
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    try:
        return OrderService(db).get_order(order_id)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.patch("/{order_id}", response_model=OrderRead, summary="Змінити наказ")
def update_order(order_id: str, data: OrderUpdate, db: Session = Depends(get_db)):
    try:
        return OrderService(db).update_order(order_id, data)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.delete(
    "/{order_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Видалити наказ"
)
def delete_order(order_id: str, db: Session = Depends(get_db)):
    try:
        OrderService(db).delete_order(order_id)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{order_id}/versions",
    response_model=OrderVersionRead,
    status_code=201,
    summary="Додати незмінну версію файла наказу",
)
def upload_order_version(
    order_id: str,
    file: UploadFile = File(...),
    change_reason: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        return OrderVersionService(db).upload(order_id, file, change_reason)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/{order_id}/versions",
    response_model=list[OrderVersionRead],
    summary="Історія версій наказу (без вмісту файлів)",
)
def list_order_versions(order_id: str, db: Session = Depends(get_db)):
    try:
        return OrderVersionService(db).list_versions(order_id)
    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/{order_id}/document", summary="")
def current_order_document(
    order_id: str, db: Session = Depends(get_db), _admin=Depends(require_admin)
):
    # Coordinators and VYK use scoped /executions/{measure_id}/{period}/document
    # so a registry URL cannot bypass measure/department authorization.
    try:
        version = OrderVersionService(db).latest(order_id)
        if version is None:
            raise HTTPException(status_code=404, detail="Файл наказу відсутній")
        path = OrderDocumentStorage().verify(version)
        return FileResponse(
            path,
            media_type=version.content_type,
            filename=version.original_filename,
            content_disposition_type=(
                "inline" if version.content_type == "application/pdf" else "attachment"
            ),
        )
    except DocumentStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
