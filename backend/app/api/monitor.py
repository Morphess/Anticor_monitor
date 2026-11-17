from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin, require_roles
from app.database.db_connection import get_db
from app.models.department import Department
from app.models.user import User
from app.services import manager_service, monitor_service

router = APIRouter(tags=["Monitor"], dependencies=[Depends(get_current_user)])


class OrderCheck(BaseModel):
    measure_id: str
    number: str


class Decision(BaseModel):
    signal_key: str = Field(max_length=60)
    decision: str
    department_id: str | None = None
    due_on: date | None = None
    comment: str = Field(default="", max_length=2000)


class StatusChange(BaseModel):
    measure_id: str
    status: str


@router.get("/admin/departments", dependencies=[Depends(require_admin)])
def admin_departments(db: Session = Depends(get_db)):
    """Довідник підрозділів для форми користувача."""
    return [{"id": d.id, "name": d.name} for d in db.scalars(select(Department).order_by(Department.name))]


@router.get("/executor/rows")
def executor_rows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Заходи підрозділу виконавця за поточний період."""
    return monitor_service.executor_page(db, user)


@router.post("/executor/check-order")
def check_order(data: OrderCheck, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Виконавець увів номер наказу й натиснув Enter."""
    return monitor_service.check_order(db, user, data.measure_id, data.number)


@router.get("/coordinator/programs")
def coordinator_programs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Програми з розділами, заходами й статусами виконання."""
    return monitor_service.coordinator_page(db, user)


@router.post("/coordinator/status")
def change_status(data: StatusChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Координатор змінює статус виконання заходу."""
    if user.role_id not in monitor_service.EDITOR_ROLES:
        raise HTTPException(status_code=403, detail="Недостатньо прав")
    try:
        return monitor_service.set_status(db, user, data.measure_id, data.status)
    except monitor_service.MonitorError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.get("/analyst/overview", dependencies=[Depends(require_roles(*monitor_service.ANALYTICS_ROLES))])
def analyst_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Зведення для аналітика: заходи всіх програм зі статусами й строками. Лише читання."""
    return monitor_service.analytics_page(db, user)


@router.get("/manager/overview", dependencies=[Depends(require_roles(*manager_service.VIEW_ROLES))])
def manager_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Рекомендації за правилами, що чекають рішення, і вже ухвалені рішення за період."""
    return manager_service.manager_page(db, user)


@router.post("/manager/decisions", dependencies=[Depends(require_roles(*manager_service.DECIDER_ROLES))])
def manager_decide(data: Decision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Керівник доручає виконати рекомендацію або відхиляє її з причиною."""
    try:
        return manager_service.decide(db, user, data.signal_key, data.decision, data.department_id,
                                      data.due_on, data.comment)
    except manager_service.ManagerError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
