"""Вхід і вихід."""
from fastapi import APIRouter, Form, Request
from sqlalchemy import select

from ..auth import HOME_BY_ROLE, LoginRequired, current_user, verify_password
from ..config import DEMO_MODE
from ..db import session
from ..models import User
from ..services import journal
from ..web import flash, redirect, render

router = APIRouter(include_in_schema=False)
ROLE_ORDER = ["KOORD", "VYK", "KER", "ANAL", "ADMIN"]


@router.get("/")
def home(request: Request):
    try:
        user = current_user(request)
    except LoginRequired:
        return redirect("/login")
    return redirect(HOME_BY_ROLE[user["role"]])


@router.get("/login")
def login_page(request: Request):
    groups = []
    if DEMO_MODE:
        rows = session().scalars(select(User).where(User.active).order_by(User.id)).all()
        groups = [(role, [u for u in rows if u.role == role]) for role in ROLE_ORDER]
    return render(request, "login.html", groups=groups)


@router.post("/login")
def login(request: Request, user_id: str = Form(""), password: str = Form("")):
    user = session().get(User, user_id.strip())
    ok = bool(user and user.active and (DEMO_MODE or verify_password(password, user.password_hash)))
    if not ok:
        flash(request, "Невірний логін або пароль" if not DEMO_MODE else "Оберіть користувача", "error")
        return redirect("/login")
    request.session.clear()
    request.session["uid"] = user.id
    journal.log(user.id, "вхід у систему", "korystuvach", user.id, request=request, commit=True)
    return redirect(HOME_BY_ROLE[user.role])


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")
