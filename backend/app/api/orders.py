"""API керування локальним реєстром наказів.

Маршрути не мають авторизації.
Для локального наповнення розробником.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.schemas.orders import OrderCreate, OrderRead, OrderUpdate
from app.services.order_services import OrderError, OrderService


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


# CREATE — створити наказ
@router.post(
    "/",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Створити наказ",
)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
):
    try:
        return OrderService(db).create_order(data)
    except OrderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


# READ — список наказів
@router.get(
    "/",
    response_model=list[OrderRead],
    summary="Переглянути накази",
)
def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return OrderService(db).list_orders(
        skip=skip,
        limit=limit,
    )


# READ — один наказ
@router.get(
    "/{order_id}",
    response_model=OrderRead,
    summary="Отримати наказ за ID",
)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    try:
        return OrderService(db).get_order(order_id)
    except OrderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


# UPDATE — редагувати наказ
@router.patch(
    "/{order_id}",
    response_model=OrderRead,
    summary="Редагувати наказ",
)
def update_order(
    order_id: str,
    data: OrderUpdate,
    db: Session = Depends(get_db),
):
    try:
        return OrderService(db).update_order(
            order_id,
            data,
        )
    except OrderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


# DELETE — видалити наказ
@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити наказ",
)
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
):
    try:
        OrderService(db).delete_order(order_id)
    except OrderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
