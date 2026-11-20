"""Доступні координатору повідомлення та захищене порівняння файлів наказу."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database.db_connection import get_db
from app.models.user import User
from app.services.measure_access import require_execution_actor
from app.services.order_change_alert_services import OrderChangeAlertService
from app.services.order_document_storage import DocumentStorageError, OrderDocumentStorage
from app.services.order_version_services import OrderVersionService
from app.services.order_services import OrderError
from app.schemas.order_versions import AlertCounter, AlertAcknowledgement

router = APIRouter(prefix="/order-change-alerts", tags=["Order Change Alerts"])


def _error(exc: OrderError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/", response_model=AlertCounter, summary="Зміни наказів у доступних заходах")
def list_alerts(
    program_id: str | None = None,
    unread_only: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
):
    try:
        return OrderChangeAlertService(db).list_alerts(
            actor, program_id=program_id, unread_only=unread_only,
            skip=skip, limit=limit,
        )
    except OrderError as exc:
        raise _error(exc) from exc


@router.post("/{alert_id}/read", response_model=AlertAcknowledgement,
             summary="Позначити повідомлення прочитаним")
def mark_read(
    alert_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
):
    try:
        return OrderChangeAlertService(db).acknowledge(alert_id, actor)
    except OrderError as exc:
        raise _error(exc) from exc


@router.get("/{alert_id}/files/{which}", summary="Завантажити перевірену версію документа")
def get_version_file(
    alert_id: int,
    which: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_execution_actor),
):
    try:
        alert = OrderChangeAlertService(db).require_alert(alert_id, actor)
        if which not in {"previous", "new"}:
            raise OrderError("Вкажи previous або new", 422)
        version_id = (alert.previous_version_id if which == "previous"
                      else alert.new_version_id)
        version = OrderVersionService(db).get(version_id)
        path = OrderDocumentStorage().verify(version)
        return FileResponse(
            path, media_type=version.content_type,
            filename=f"order-{alert.order_id}-v{version.version}{path.suffix}",
        )
    except OrderError as exc:
        raise _error(exc) from exc
    except DocumentStorageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
