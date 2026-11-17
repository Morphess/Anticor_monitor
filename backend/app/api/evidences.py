from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db

from app.models.user import User
from app.models.measure import Measure

from app.schemas.evidences import EvidenceCreate, EvidenceRead, EvidenceUpdate

from app.services.evidence_services import EvidenceError, EvidenceService


router = APIRouter(
    prefix="/evidences", tags=["Evidences"], dependencies=[Depends(get_current_user)]
)


# Перевірка прав на редагування документів заходу
def check_edit_access(user: User, measure: Measure) -> None:

    # Адміністратор має повний доступ
    if user.role_id == "ADMIN":
        return

    # Координатор працює лише зі своєю програмою
    if user.role_id == "KOORD":
        if user.program_id is not None and user.program_id == measure.program_id:
            return

    # Виконавець працює лише з призначеним заходом
    if user.role_id == "VYK":
        if measure.assigned_user_id == user.id:
            return

    raise HTTPException(status_code=403, detail="Недостатньо прав для цього заходу")


# Отримання заходу та перевірка прав
def get_editable_measure(db: Session, user: User, measure_id: str) -> Measure:

    measure = db.get(Measure, measure_id)

    if measure is None:
        raise HTTPException(status_code=422, detail="Захід не існує")

    check_edit_access(user, measure)

    return measure


# CREATE — створити документ
@router.post("/", response_model=EvidenceRead, status_code=201)
def create_evidence(
    data: EvidenceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    # Перевіряємо доступ до заходу
    get_editable_measure(db, user, data.measure_id)

    try:
        return EvidenceService(db).create_evidence(data)

    except EvidenceError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# READ — список документів
@router.get("/", response_model=list[EvidenceRead])
def list_evidences(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    measure_id: str | None = None,
    db: Session = Depends(get_db),
):

    return EvidenceService(db).list_evidences(skip, limit, measure_id)


# READ — один документ
@router.get("/{evidence_id}", response_model=EvidenceRead)
def get_evidence(evidence_id: str, db: Session = Depends(get_db)):

    try:
        return EvidenceService(db).get_evidence(evidence_id)

    except EvidenceError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# UPDATE — редагувати документ
@router.patch("/{evidence_id}", response_model=EvidenceRead)
def update_evidence(
    evidence_id: str,
    data: EvidenceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    service = EvidenceService(db)

    try:
        evidence = service.get_evidence(evidence_id)

        # Перевіряємо доступ до поточного заходу
        get_editable_measure(db, user, evidence.measure_id)

        # Якщо документ переноситься до іншого заходу,
        # перевіряємо доступ і до нового заходу
        if data.measure_id is not None:
            get_editable_measure(db, user, data.measure_id)

        return service.update_evidence(evidence_id, data)

    except EvidenceError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# DELETE — видалити документ
@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    service = EvidenceService(db)

    try:
        evidence = service.get_evidence(evidence_id)

        # Перевіряємо права перед видаленням
        get_editable_measure(db, user, evidence.measure_id)

        service.delete_evidence(evidence_id)

    except EvidenceError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
