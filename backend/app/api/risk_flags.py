"""API Risk Flags: MAIN_KOORD — свої програми; KOORD — доступна гілка.

Ні ADMIN, ні VYK, ні інші ролі не можуть викликати ці маршрути.
Risk Flags обчислюються на запит; записів у БД цей API не створює.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.repositories.risk_flag_repository import RiskFlagRepository
from app.schemas.risk_flags import RiskFlagRead
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError
from app.services.risk_flag_services import detect_risk_flags, detect_rf8_flags, period_bounds


ALLOWED_ROLES = frozenset({"MAIN_KOORD", "KOORD"})

router = APIRouter(
    prefix="/risk-flags",
    tags=["Risk Flags"],
    responses={
        401: {"description": "Потрібна авторизація"},
        403: {"description": "Недостатньо прав або немає доступу до програми"},
        404: {"description": "Програму не знайдено"},
    },
)


def require_risk_flags_reader(
    user: User = Depends(get_current_user),
) -> User:
    """Дозволяє переглядати сигнали лише MAIN_KOORD та KOORD."""
    if user.role_id not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Сигнали доступні лише MAIN_KOORD та KOORD",
        )
    return user


@router.get(
    "/",
    response_model=list[RiskFlagRead],
    summary="Отримати сигнали ризиків програми",
    description=(
        "**MAIN_KOORD** переглядає всі сигнали у своїй програмі, зокрема "
        "RF7d для ризиків без заходів. **KOORD** переглядає лише сигнали "
        "доступних заходів, а також RF7d для ризиків, власником яких є "
        "його підрозділ або його нащадки. Доступ до програми перевіряється "
        "через `program-routing`; `user.program_id` не використовується. "
        "**ADMIN**, **VYK**, **KER**, **ANAL** — без доступу. "
        "Дані відбираються на рівні SQL до аналізу Risk Flags."
    ),
    response_description="Сигнали лише у межах прав користувача та обраної програми",
)
def list_risk_flags(
    program_id: str = Query(
        ..., min_length=1, max_length=50,
        description="ID програми, наприклад AKP-2026",
    ),
    period: str = Query(
        default="2026-H1", pattern=r"^\d{4}-H[12]$",
        description="Звітне півріччя у форматі YYYY-H1 або YYYY-H2",
    ),
    as_of: date = Query(
        ..., description="Дата зрізу; для code=RF8 допускається поточне незавершене півріччя",
    ),
    code: str | None = Query(
        default=None, description="Фільтр за кодом, наприклад RF1 або RF7d",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_risk_flags_reader),
) -> list[RiskFlagRead]:
    """Перевірити роль → програму → заходи → підрозділи → сформувати сигнали."""
    try:
        period_start, period_end = period_bounds(period)
        if code == "RF8":
            if as_of < period_start:
                raise ValueError("Дата зрізу для RF8 не може бути раніше початку періоду")
        elif as_of < period_end:
            raise ValueError("Дата зрізу не може бути раніше кінця періоду")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    workflow = ProgramWorkflowService(db)
    try:
        # Ця перевірка важлива навіть коли в програмі НЕМАЄ заходів:
        # MAIN_KOORD повинен отримати RF7d для високих ризиків без заходів.
        workflow.visible_program(program_id, user)
        visible_measures = workflow.program_measures(program_id, user)

        department_scope: set[str] | None = ({user.department_id} if user.department_id else None)
        if user.role_id == "KOORD":
            if not user.department_id:
                raise HTTPException(
                    status_code=403,
                    detail="Для KOORD не визначено підрозділ",
                )
            department_scope = workflow.tree.descendants(user.department_id)
            if not department_scope:
                raise HTTPException(
                    status_code=403,
                    detail="Підрозділ координатора відсутній в ієрархії",
                )
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    allowed_ids = {m["id"] for m in visible_measures}
    snapshot = RiskFlagRepository(db).snapshot(
        program_id=program_id,
        period=period,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        visible_measure_ids=allowed_ids,
        allowed_risk_department_ids=department_scope,
    )
    if code == "RF8":
        # RF8 працює і ДО завершення півріччя; інші коди — за попереднім правилом.
        flags = detect_rf8_flags(
            period=period, as_of=as_of,
            measures=snapshot["measures"],
            invalid_order_attempts=snapshot["invalid_order_attempts"],
        )
    else:
        flags = detect_risk_flags(period=period, as_of=as_of, **snapshot)

    if user.role_id == "KOORD":
        # Агрегат RF6 створюється за responsible_department_id заходів.
        # Видимий захід може мати відповідального поза своєю гілкою
        # (коли свій підрозділ є співвиконавцем). Чужі агрегати не показуємо.
        flags = [
            flag for flag in flags
            if flag.object_type != "pidrozdil" or flag.object_id in department_scope
        ]

    return [flag for flag in flags if code is None or flag.code == code]
