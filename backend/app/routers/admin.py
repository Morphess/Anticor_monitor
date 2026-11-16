"""Адміністрування: користувачі, звітний період, дата зрізу, повторний імпорт набору."""
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select

from ..auth import hash_password, require_role
from ..db import session
from ..models import Unit, User
from ..services import journal, monitor, rules
from ..utils import parse_date, period_bounds
from ..web import flash, redirect, render

router = APIRouter(include_in_schema=False)
admin = require_role("ADMIN")


@router.get("/admin")
def admin_page(request: Request, user: dict = Depends(admin)):
    s = session()
    users = s.scalars(select(User).order_by(User.id)).all()
    units = {u.id: u.name for u in s.scalars(select(Unit))}
    return render(request, "admin.html", user, users=users, units=units)


@router.post("/admin/period")
def set_period(request: Request, period: str = Form(""), as_of: str = Form(""),
               user: dict = Depends(require_role("ADMIN", "KOORD"))):
    back = "/admin" if user["role"] == "ADMIN" else "/review"
    try:
        period_bounds(period)
    except Exception:
        flash(request, "Період вказують так: 2026-H1 або 2026-H2", "error")
        return redirect(back)
    day = parse_date(as_of)
    if as_of and not day:
        flash(request, "Невірна дата зрізу", "error")
        return redirect(back)
    old = monitor.current_period()
    if old != period:
        monitor.set_setting("period", period)
        journal.log(user["id"], "змінено звітний період", "nalashtuvannia", "period", "period", old, period, request)
    old_day = monitor.get_setting("as_of") or ""
    new_day = day.isoformat() if day else None
    if (new_day or "") != old_day:
        monitor.set_setting("as_of", new_day)
        journal.log(user["id"], "змінено дату зрізу", "nalashtuvannia", "as_of", "as_of", old_day, new_day or "", request)
    session().commit()
    flash(request, "Збережено")
    return redirect(back)


@router.post("/admin/users/{user_id}")
def update_user(request: Request, user_id: str, active: str = Form(""), password: str = Form(""),
                user: dict = Depends(admin)):
    s = session()
    target = s.get(User, user_id)
    if not target:
        flash(request, "Користувача не знайдено", "error")
        return redirect("/admin")
    new_active = active == "1"
    if target.id == user["id"] and not new_active:
        flash(request, "Не можна вимкнути власний обліковий запис", "error")
        return redirect("/admin")
    if target.active != new_active:
        journal.log(user["id"], "змінено доступ користувача", "korystuvach", target.id, "active",
                    "так" if target.active else "ні", "так" if new_active else "ні", request)
        target.active = new_active
    if password:
        if len(password) < 10:
            flash(request, "Пароль — не менше 10 символів", "error")
            return redirect("/admin")
        target.password_hash = hash_password(password)
        journal.log(user["id"], "задано пароль", "korystuvach", target.id, "password", "", "(приховано)", request)
    s.commit()
    flash(request, f"{target.id} ({rules.ROLES.get(target.role, target.role)}): збережено")
    return redirect("/admin")
