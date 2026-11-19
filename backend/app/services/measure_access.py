"""Спільні правила доступу до заходів для виконань і підтверджень.

MAIN_KOORD: лише власні програми (created_by_user_id).
KOORD: лише явно направлені програми та доступні заходи за ієрархією.
VYK: персональні призначення з measure_assignments.
ADMIN / KER / ANAL: доступ заборонений.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.measure import Measure
from app.models.program import Program
from app.models.program_workflow import ProgramDepartment
from app.models.user import User
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError

ALLOWED_ROLES = frozenset({"MAIN_KOORD", "KOORD", "VYK"})


def require_execution_actor(user: User = Depends(get_current_user)) -> User:
    """Забороняє доступ до Executions/Evidences всім іншим ролям."""
    if user.role_id not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ лише для MAIN_KOORD, KOORD та VYK",
        )
    return user


def require_executor(user: User = Depends(require_execution_actor)) -> User:
    """Створення/редагування виконання або підтвердження — лише VYK."""
    if user.role_id != "VYK":
        raise HTTPException(status_code=403, detail="Ця дія доступна лише виконавцю (VYK)")
    return user


def require_department_coordinator(
    user: User = Depends(require_execution_actor),
) -> User:
    """Погоджувати виконання може тільки підрозділовий KOORD."""
    if user.role_id != "KOORD":
        raise HTTPException(status_code=403, detail="Погодження доступне лише KOORD")
    return user


def _run_workflow(callback):
    try:
        return callback()
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def visible_measure_ids(
    db: Session,
    actor: User,
    program_id: str | None = None,
) -> set[str]:
    """Повертає лише ID заходів, на які actor має доступ за програмним workflow.

    Призначення/власність перевіряє ProgramWorkflowService, а не старі поля
    users.program_id чи measures.assigned_user_id.
    """
    if actor.role_id not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Немає доступу до заходів")

    workflow = ProgramWorkflowService(db)
    if actor.role_id == "VYK":
        # my_measures() вже перевіряє персональні призначення та направлення.
        rows = _run_workflow(lambda: workflow.my_measures(actor))
        return {
            row["id"]
            for row in rows
            if program_id is None or row["program_id"] == program_id
        }

    if actor.role_id == "MAIN_KOORD":
        stmt = select(Program.id).where(Program.created_by_user_id == actor.id)
    else:
        if not actor.department_id:
            return set()
        stmt = select(ProgramDepartment.program_id).where(
            ProgramDepartment.department_id == actor.department_id
        )
    if program_id is not None:
        if actor.role_id == "MAIN_KOORD":
            stmt = stmt.where(Program.id == program_id)
        else:
            stmt = stmt.where(ProgramDepartment.program_id == program_id)

    result: set[str] = set()
    for pid in db.scalars(stmt.distinct()):
        rows = _run_workflow(lambda pid=pid: workflow.program_measures(pid, actor))
        result.update(row["id"] for row in rows)
    return result


def require_visible_measure(db: Session, actor: User, measure_id: str) -> Measure:
    """404 — невідомий захід, 403 — відсутні права на нього."""
    if actor.role_id not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Немає доступу")
    measure = db.get(Measure, measure_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Захід не знайдено")
    if measure_id not in visible_measure_ids(db, actor, measure.program_id):
        raise HTTPException(status_code=403, detail="Немає доступу до цього заходу")
    return measure
