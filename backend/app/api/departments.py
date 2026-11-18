from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_admin
from app.database.db_connection import get_db
from app.schemas.departments import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
)
from app.services.department_services import DepartmentService


router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[DepartmentRead])
def list_departments(db: Session = Depends(get_db)):
    return DepartmentService(db).get_all()


@router.get("/{department_id}", response_model=DepartmentRead)
def get_department(
    department_id: str,
    db: Session = Depends(get_db),
):
    return DepartmentService(db).get_by_id(department_id)


@router.post(
    "",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
):
    return DepartmentService(db).create(data)


@router.patch("/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: str,
    data: DepartmentUpdate,
    db: Session = Depends(get_db),
):
    return DepartmentService(db).update(department_id, data)


@router.delete(
    "/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_department(
    department_id: str,
    db: Session = Depends(get_db),
):
    DepartmentService(db).delete(department_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)