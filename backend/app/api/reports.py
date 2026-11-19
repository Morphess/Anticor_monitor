"""API звітів програм: доступ лише MAIN_KOORD та KOORD.

MAIN_KOORD: створює, переглядає, оновлює й видаляє звіти власних програм.
KOORD: створює звіти направлених його підрозділу програм та працює
       лише зі звітами, створеними ним самим.
ADMIN, VYK, KER, ANAL: жодних операцій із цими маршрутами.

Звіт прив'язаний до програми. У поточній моделі Report немає department_id,
тому власність звіту KOORD перевіряється через generated_by_user_id.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.program import Program
from app.models.program_workflow import ProgramDepartment
from app.models.report import Report
from app.models.user import User
from app.schemas.reports import ReportCreate, ReportRead, ReportUpdate
from app.services.report_services import ReportError, ReportService
from app.schemas.report_portal import PortalHalfYearReport
from app.services.report_generation_service import (
    ReportGenerationService, csv_export, print_html,
)


ALLOWED_REPORT_ROLES = frozenset({"MAIN_KOORD", "KOORD"})


def require_report_role(user: User = Depends(get_current_user)) -> User:
    """Забороняє будь-які операції зі звітами для ADMIN та інших ролей."""
    if user.role_id not in ALLOWED_REPORT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Звіти доступні лише MAIN_KOORD та KOORD",
        )
    return user


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(require_report_role)],
)


def _main_owns_program(db: Session, user: User, program_id: str) -> bool:
    """MAIN_KOORD може працювати лише з програмами, які сам створив."""
    if user.role_id != "MAIN_KOORD":
        return False
    program = db.get(Program, program_id)
    return program is not None and program.created_by_user_id == user.id


def _koord_received_program(db: Session, user: User, program_id: str) -> bool:
    """KOORD має отримати програму напряму на свій підрозділ."""
    return bool(
        user.role_id == "KOORD"
        and user.department_id
        and db.get(ProgramDepartment, (program_id, user.department_id)) is not None
    )


def _ensure_program_access(db: Session, user: User, program_id: str) -> None:
    """Перевіряє доступ до програми відповідно до нової моделі маршрутизації."""
    if _main_owns_program(db, user, program_id) or _koord_received_program(
        db, user, program_id
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Немає доступу до звітів цієї програми",
    )


def _ensure_report_access(db: Session, user: User, report: Report) -> None:
    """MAIN_KOORD бачить звіти власних програм; KOORD — лише свої."""
    _ensure_program_access(db, user, report.program_id)
    if user.role_id == "KOORD" and report.generated_by_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="KOORD може працювати лише зі звітами, створеними ним",
        )


@router.post(
    "/",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Створити звіт програми",
    description=(
        "Тільки MAIN_KOORD для своєї програми або KOORD для програми, "
        "направленої його підрозділу. ADMIN не має доступу. "
        "Автор визначається за JWT."
    ),
)
def create_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    _ensure_program_access(db, user, data.program_id)
    try:
        return ReportService(db).create_report(data, user.id)
    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.get(
    "/",
    response_model=list[ReportRead],
    summary="Переглянути доступні звіти",
    description=(
        "MAIN_KOORD бачить звіти власних програм. KOORD бачить лише "
        "свої звіти програм, прямо направлених його підрозділу. "
        "ADMIN та інші ролі отримують 403."
    ),
)
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    program_id: str | None = None,
    period: str | None = None,
    status_filter: Literal["draft", "generated", "submitted"] | None = Query(
        default=None, alias="status"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    if program_id is not None:
        _ensure_program_access(db, user, program_id)

    query = select(Report)
    if user.role_id == "MAIN_KOORD":
        query = query.join(Program, Report.program_id == Program.id).where(
            Program.created_by_user_id == user.id
        )
    else:  # KOORD; жодна інша роль сюди не потрапляє
        if not user.department_id:
            return []
        query = query.join(
            ProgramDepartment, ProgramDepartment.program_id == Report.program_id
        ).where(
            ProgramDepartment.department_id == user.department_id,
            Report.generated_by_user_id == user.id,
        )

    if program_id is not None:
        query = query.where(Report.program_id == program_id)
    if period is not None:
        query = query.where(Report.period == period)
    if status_filter is not None:
        query = query.where(Report.status == status_filter)

    query = query.order_by(Report.id).offset(skip).limit(limit)
    return db.scalars(query).all()


# NEW: попередній розрахунок із живих даних, НЕ створює версію у БД.
@router.get(
    "/preview",
    response_model=PortalHalfYearReport,
    summary="Попередній піврічний звіт (без збереження)",
)
def preview_report(
    program_id: str,
    period: str = Query(pattern=r"^\d{4}-H[12]$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    _ensure_program_access(db, user, program_id)
    try:
        return ReportGenerationService(db).build(program_id, period, user)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# NEW: одна дія створює наступну версію та незмінний снепшот.
@router.post(
    "/auto-generate",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Автоматично сформувати нову версію звіту",
)
def auto_generate_report(
    program_id: str,
    period: str = Query(pattern=r"^\d{4}-H[12]$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    _ensure_program_access(db, user, program_id)
    try:
        return ReportGenerationService(db).auto_generate(program_id, period, user)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# NEW: сформувати вже створену чернетку.
@router.post(
    "/{report_id}/generate",
    response_model=ReportRead,
    summary="Згенерувати вміст чернетки",
)
def generate_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    report = ReportService(db).get_report(report_id)
    _ensure_report_access(db, user, report)
    try:
        return ReportGenerationService(db).generate_draft(report, user)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# NEW: версіонований JSON саме тієї версії, яку зберегли.
@router.get(
    "/{report_id}/content",
    response_model=PortalHalfYearReport,
    summary="Вміст збереженої версії звіту",
)
def get_report_content(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    try:
        report = ReportService(db).get_report(report_id)
        _ensure_report_access(db, user, report)
        return ReportGenerationService(db).read_snapshot(report)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/{report_id}/download.csv", summary="Завантажити CSV звіту")
def download_report_csv(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    try:
        report = ReportService(db).get_report(report_id)
        _ensure_report_access(db, user, report)
        snapshot = ReportGenerationService(db).read_snapshot(report)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    filename = f"report_{report.id}_{report.period}.csv"
    return Response(
        content=csv_export(snapshot),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}/print", summary="Друкована форма звіту (HTML)")
def print_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    try:
        report = ReportService(db).get_report(report_id)
        _ensure_report_access(db, user, report)
        snapshot = ReportGenerationService(db).read_snapshot(report)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=print_html(snapshot), media_type="text/html; charset=utf-8")


@router.get(
    "/{report_id}",
    response_model=ReportRead,
    summary="Отримати звіт за ID",
    description="Звіт доступний лише уповноваженим MAIN_KOORD або його автору KOORD.",
)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    try:
        report = ReportService(db).get_report(report_id)
    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    _ensure_report_access(db, user, report)
    return report


@router.patch(
    "/{report_id}",
    response_model=ReportRead,
    summary="Оновити звіт",
    description=(
        "MAIN_KOORD оновлює звіти власних програм; KOORD — лише свої звіти "
        "програм, направлених його підрозділу. "
        "Змінювати автора та програму звіту заборонено."
    ),
)
def update_report(
    report_id: int,
    data: ReportUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    service = ReportService(db)
    try:
        report = service.get_report(report_id)
    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    _ensure_report_access(db, user, report)

    updates = data.model_dump(exclude_unset=True)
    if "program_id" in updates and updates["program_id"] != report.program_id:
        raise HTTPException(status_code=422, detail="Не можна змінювати програму звіту")
    if (
        "generated_by_user_id" in updates
        and updates["generated_by_user_id"] != report.generated_by_user_id
    ):
        raise HTTPException(status_code=422, detail="Не можна змінювати автора звіту")

    try:
        return service.update_report(report_id, data)
    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалити звіт",
    description=(
        "Тільки MAIN_KOORD для звітів власних програм або KOORD для "
        "власних звітів направленої програми. ADMIN не має доступу."
    ),
)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_report_role),
):
    service = ReportService(db)
    try:
        report = service.get_report(report_id)
    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    _ensure_report_access(db, user, report)

    try:
        service.delete_report(report_id)
    except ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
