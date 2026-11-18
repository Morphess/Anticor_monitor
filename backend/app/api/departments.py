from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db
from app.schemas.departments import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services.department_services import (
    DepartmentAlreadyExistsError,
    DepartmentNotFoundError,
    DepartmentService,
    DepartmentUpdateError,
)


router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
    dependencies=[Depends(require_admin)],
)


@router.get("/", response_model=list[DepartmentRead])
def list_departments(db: Session = Depends(get_db)):
    return DepartmentService(db).list_departments()


@router.post(
    "/",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_department(data: DepartmentCreate, db: Session = Depends(get_db)):
    try:
        return DepartmentService(db).create_department(data)
    except DepartmentAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.patch("/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: str,
    data: DepartmentUpdate,
    db: Session = Depends(get_db),
):
    try:
        return DepartmentService(db).update_department(department_id, data)
    except DepartmentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DepartmentUpdateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
