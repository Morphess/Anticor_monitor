from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User

from app.schemas.measures import MeasureCreate, MeasureRead, MeasureUpdate

from app.services.measure_services import MeasureError, MeasureService


# Перевірка права редагування заходів
def require_measure_editor(user: User = Depends(get_current_user)) -> User:

    if user.role_id not in ("ADMIN", "KOORD"):
        raise HTTPException(status_code=403, detail="Недостатньо прав")

    return user


router = APIRouter(
    prefix="/measures", tags=["Measures"], dependencies=[Depends(get_current_user)]
)


# Перетворюємо помилки Service на HTTP-помилки
def service_error(exc: MeasureError) -> HTTPException:

    return HTTPException(status_code=exc.status_code, detail=str(exc))


# CREATE — створити захід
@router.post("/", response_model=MeasureRead, status_code=201)
def create_measure(
    data: MeasureCreate,
    db: Session = Depends(get_db),
    _editor: User = Depends(require_measure_editor),
):
    try:
        return MeasureService(db).create_measure(data)

    except MeasureError as exc:
        raise service_error(exc) from exc


# READ — список заходів
@router.get("/", response_model=list[MeasureRead])
def list_measures(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    program_id: str | None = None,
    section_id: str | None = None,
    db: Session = Depends(get_db),
):
    return MeasureService(db).list_measures(skip, limit, program_id, section_id)


# READ — один захід
@router.get("/{measure_id}", response_model=MeasureRead)
def get_measure(measure_id: str, db: Session = Depends(get_db)):
    try:
        return MeasureService(db).get_measure(measure_id)

    except MeasureError as exc:
        raise service_error(exc) from exc


# UPDATE — змінити захід
@router.patch("/{measure_id}", response_model=MeasureRead)
def update_measure(
    measure_id: str,
    data: MeasureUpdate,
    db: Session = Depends(get_db),
    _editor: User = Depends(require_measure_editor),
):
    try:
        return MeasureService(db).update_measure(measure_id, data)

    except MeasureError as exc:
        raise service_error(exc) from exc


# DELETE — видалити захід
@router.delete("/{measure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_measure(
    measure_id: str,
    db: Session = Depends(get_db),
    _editor: User = Depends(require_measure_editor),
):
    try:
        MeasureService(db).delete_measure(measure_id)

    except MeasureError as exc:
        raise service_error(exc) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
