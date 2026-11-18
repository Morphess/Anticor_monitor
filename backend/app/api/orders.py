from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db

from app.models.measure import Measure
from app.models.user import User

from app.schemas.orders import OrderCreate, OrderRead, OrderUpdate
from app.services.order_services import OrderError, OrderService


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
    dependencies=[Depends(get_current_user)],
)


# Перевірка можливості перегляду наказу
def _read_allowed(user: User, measure: Measure) -> bool:

    if user.role_id == "ADMIN":
        return True

    if user.role_id == "VYK":
        return measure.assigned_user_id == user.id

    return (
        user.role_id in {"KOORD", "KER", "ANAL"}
        and user.program_id is not None
        and user.program_id == measure.program_id
    )


def _require_read_access(user: User, measure: Measure) -> None:

    if not _read_allowed(user, measure):
        raise HTTPException(
            status_code=403, detail="Немає доступу до наказів цього заходу"
        )


# Перевірка прав на створення і зміну
def _require_edit_access(user: User, measure: Measure) -> None:

    if user.role_id == "ADMIN":
        return

    if (
        user.role_id == "KOORD"
        and user.program_id is not None
        and user.program_id == measure.program_id
    ):
        return

    raise HTTPException(status_code=403, detail="Недостатньо прав для зміни наказу")


# Отримати пов'язаний захід
def _get_measure(db: Session, measure_id: str) -> Measure:

    measure = db.get(Measure, measure_id)

    if measure is None:
        raise HTTPException(status_code=422, detail="Захід не знайдено")

    return measure


# CREATE — створити наказ
@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    _require_edit_access(user, _get_measure(db, data.measure_id))

    try:
        return OrderService(db).create_order(data)

    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# READ — список наказів
@router.get("/", response_model=list[OrderRead])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    measure_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    if user.role_id == "ADMIN":
        scope = {}

    elif user.role_id == "VYK":
        scope = {"assigned_user_id": user.id}

    elif user.role_id in {"KOORD", "KER", "ANAL"} and user.program_id is not None:
        scope = {"program_id": user.program_id}

    else:
        raise HTTPException(status_code=403, detail="Немає доступу до наказів")

    return OrderService(db).list_orders(
        skip=skip, limit=limit, measure_id=measure_id, **scope
    )


# READ — отримати наказ за ID
@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    try:
        order = OrderService(db).get_order(order_id)

    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    _require_read_access(user, _get_measure(db, order.measure_id))

    return order


# UPDATE — редагувати наказ
@router.patch("/{order_id}", response_model=OrderRead)
def update_order(
    order_id: str,
    data: OrderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    service = OrderService(db)

    try:
        order = service.get_order(order_id)

        # Перевіряємо доступ до поточного заходу
        _require_edit_access(user, _get_measure(db, order.measure_id))

        # Якщо змінюється захід, перевіряємо
        # доступ до нового заходу
        if data.measure_id is not None:
            _require_edit_access(user, _get_measure(db, data.measure_id))

        return service.update_order(order_id, data)

    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# DELETE — видалити наказ
@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    if user.role_id != "ADMIN":
        raise HTTPException(status_code=403, detail="Видаляти накази може лише ADMIN")

    try:
        OrderService(db).delete_order(order_id)

    except OrderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
