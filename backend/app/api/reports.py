from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User

from app.schemas.reports import ReportCreate, ReportRead, ReportUpdate
from app.services.report_services import ReportError, ReportService


router = APIRouter(prefix="/reports", tags=["Reports"])


# Перевірка права перегляду звіту
def check_read_access(user: User, program_id: str) -> None:

    if user.role_id == "ADMIN":
        return

    if user.program_id is not None and user.program_id == program_id:
        return

    raise HTTPException(status_code=403, detail="Немає доступу до звітів цієї програми")


# Перевірка права редагування звіту
def check_edit_access(user: User, program_id: str) -> None:

    if user.role_id == "ADMIN":
        return

    if (
        user.role_id == "KOORD"
        and user.program_id is not None
        and user.program_id == program_id
    ):
        return

    raise HTTPException(status_code=403, detail="Недостатньо прав для зміни звіту")


# CREATE — створити звіт
@router.post("/", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    check_edit_access(user, data.program_id)

    try:
        return ReportService(db).create_report(data, user.id)

    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# READ — список звітів
@router.get("/", response_model=list[ReportRead])
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    program_id: str | None = None,
    period: str | None = None,
    status_filter: Literal["draft", "generated", "submitted"] | None = Query(
        default=None, alias="status"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    # Неадміністратор бачить тільки свою програму
    if user.role_id != "ADMIN":

        if user.program_id is None:
            raise HTTPException(
                status_code=403, detail="Користувач не прив'язаний до програми"
            )

        if program_id is not None and program_id != user.program_id:
            raise HTTPException(
                status_code=403, detail="Немає доступу до цієї програми"
            )

        program_id = user.program_id

    return ReportService(db).list_reports(
        skip=skip,
        limit=limit,
        program_id=program_id,
        period=period,
        status=status_filter,
    )


# READ — отримати один звіт
@router.get("/{report_id}", response_model=ReportRead)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    try:
        report = ReportService(db).get_report(report_id)

        check_read_access(user, report.program_id)

        return report

    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# UPDATE — редагувати звіт
@router.patch("/{report_id}", response_model=ReportRead)
def update_report(
    report_id: int,
    data: ReportUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    service = ReportService(db)

    try:
        report = service.get_report(report_id)

        check_edit_access(user, report.program_id)

        return service.update_report(report_id, data)

    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


# DELETE — видалити чернетку
@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    # Видалення доступне тільки адміністратору
    if user.role_id != "ADMIN":
        raise HTTPException(
            status_code=403, detail="Видаляти звіти може лише адміністратор"
        )

    try:
        ReportService(db).delete_report(report_id)

    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
