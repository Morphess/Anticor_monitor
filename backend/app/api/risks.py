from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.main_coordinator import require_main_coordinator
from app.database.db_connection import get_db

from app.schemas.risks import RiskCreate, RiskRead, RiskUpdate
from app.services.risk_services import RiskError, RiskService


router = APIRouter(
    prefix="/risks", tags=["Risks"], dependencies=[Depends(require_main_coordinator)]
)


# CREATE - створити ризик
@router.post(
    "/",
    response_model=RiskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_risk(data: RiskCreate, db: Session = Depends(get_db)):
    try:
        return RiskService(db).create_risk(data)

    except RiskError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# READ - список ризиків
@router.get("/", response_model=list[RiskRead])
def list_risks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    owner_department_id: str | None = None,
    db: Session = Depends(get_db),
):
    return RiskService(db).list_risks(skip, limit, owner_department_id)


# READ - один ризик
@router.get("/{risk_id}", response_model=RiskRead)
def get_risk(risk_id: str, db: Session = Depends(get_db)):
    try:
        return RiskService(db).get_risk(risk_id)

    except RiskError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# UPDATE - редагувати ризик
@router.patch(
    "/{risk_id}",
    response_model=RiskRead,
)
def update_risk(risk_id: str, data: RiskUpdate, db: Session = Depends(get_db)):
    try:
        return RiskService(db).update_risk(risk_id, data)

    except RiskError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# DELETE - видалити ризик
@router.delete(
    "/{risk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_risk(risk_id: str, db: Session = Depends(get_db)):
    try:
        RiskService(db).delete_risk(risk_id)

    except RiskError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
