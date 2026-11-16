"""Точка входу: cd backend && uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .auth import LoginRequired
from .config import AUTO_IMPORT, FRONTEND_DIR, SECRET_KEY
from .db import init_db, session, session_scope
from .models import User
from .routers import admin, api, auth, pages, work
from .web import redirect, render


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # створює таблиці, якщо їх ще немає
    with session_scope() as s:
        empty = not s.scalar(select(func.count()).select_from(User))
    if AUTO_IMPORT and empty:
        from .importer import import_dataset

        import_dataset(reset=False)
    yield


class DBSessionMiddleware:
    """Окрема сесія бази на кожен HTTP-запит (чисте ASGI-middleware)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        with session_scope():
            await self.app(scope, receive, send)


app = FastAPI(title="Моніторинг виконання антикорупційної програми", version="0.1.0", lifespan=lifespan,
              description="API для інтеграції: стан програми, заходи, ризики, сигнали, звіт у структурі Порталу.")
app.add_middleware(DBSessionMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=8 * 3600, same_site="lax")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

for module in (auth, pages, work, admin, api):
    app.include_router(module.router)


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


@app.exception_handler(LoginRequired)
async def login_required(request: Request, exc: LoginRequired):
    if _is_api(request):
        return JSONResponse({"detail": "Потрібен вхід"}, status_code=401)
    return redirect("/login")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if _is_api(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return render(request, "error.html", status_code=exc.status_code, code=exc.status_code, message=exc.detail)


@app.get("/health", include_in_schema=False)
def health():
    session().execute(text("SELECT 1"))
    return {"status": "ok"}
