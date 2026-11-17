from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin
from app.database.db_connection import get_db
from app.models.user import User
from app.models.measure import Measure

from app.schemas.deadline_changes import (
    DeadlineChangeCreate,
    DeadlineChangeRead,
    DeadlineChangeUpdate,
)
from app.services.deadline_change_services import (
    DeadlineChangeError,
    DeadlineChangeService,
)


router = APIRouter(
    prefix="/deadline-changes",
    tags=["Deadline Changes"],
    dependencies=[Depends(get_current_user)],
)


# Перевірка прав на зміну строків
def check_edit_access(user: User, measure: Measure) -> None:

    # Адміністратор
    if user.role_id == "ADMIN":
        return

    # Координатор своєї програми
    if user.role_id == "KOORD":
        if user.program_id is not None and user.program_id == measure.program_id:
            return

    raise HTTPException(
        status_code=403, detail="Недостатньо прав для перенесення строку"
    )


# CREATE — створити перенесення
@router.post("/", response_model=DeadlineChangeRead, status_code=201)
def create_change(
    data: DeadlineChangeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    measure = db.get(Measure, data.measure_id)

    if measure is None:
        raise HTTPException(status_code=422, detail="Захід не існує")

    check_edit_access(user, measure)

    try:
        return DeadlineChangeService(db).create_change(data, user.id)

    except DeadlineChangeError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# READ — список перенесень
@router.get("/", response_model=list[DeadlineChangeRead])
def list_changes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    measure_id: str | None = None,
    db: Session = Depends(get_db),
):

    return DeadlineChangeService(db).list_changes(skip, limit, measure_id)


# READ — одне перенесення
@router.get("/{change_id}", response_model=DeadlineChangeRead)
def get_change(change_id: int, db: Session = Depends(get_db)):

    try:
        return DeadlineChangeService(db).get_change(change_id)

    except DeadlineChangeError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# UPDATE — редагувати перенесення
@router.patch("/{change_id}", response_model=DeadlineChangeRead)
def update_change(
    change_id: int,
    data: DeadlineChangeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    service = DeadlineChangeService(db)

    try:
        change = service.get_change(change_id)

        measure = db.get(Measure, change.measure_id)

        if measure is None:
            raise HTTPException(status_code=404, detail="Захід не знайдено")

        check_edit_access(user, measure)

        return service.update_change(change_id, data)

    except DeadlineChangeError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# DELETE — видалити перенесення
@router.delete(
    "/{change_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete_change(change_id: int, db: Session = Depends(get_db)):

    try:
        DeadlineChangeService(db).delete_change(change_id)

    except DeadlineChangeError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
