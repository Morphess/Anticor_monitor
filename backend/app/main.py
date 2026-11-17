from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.db_connection import get_db, engine

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.programs import router as programs_router
from app.api.sections import router as sections_router
from app.api.measures import router as measures_router


# Коренева папка проєкту
BASE_DIR = Path(__file__).resolve().parents[2]

# Папки фронтенду
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"


# Життєвий цикл застосунку
@asynccontextmanager
async def lifespan(app: FastAPI):

    print("Anticor Monitor запускається...")

    try:
        yield  # FastAPI працює тут
    finally:
        engine.dispose()
        print("Anticor Monitor завершив роботу.")


# Створення FastAPI
app = FastAPI(title="Anticor Monitor", lifespan=lifespan)


# Підключення API
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(programs_router, prefix="/api")
app.include_router(sections_router, prefix="/api")
app.include_router(measures_router, prefix="/api")


# HTML-шаблони
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Статичні файли
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Головна сторінка
@app.get("/")
def read_root():
    return {"app": "Anticor Monitor", "status": "running"}


# Перевірка PostgreSQL
@app.get("/db")
def database_health_check(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("SELECT 1")).scalar()

        return {"status": "connected", "database": "PostgreSQL", "result": result}

    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503, detail="Не вдалося підключитися до PostgreSQL"
        ) from error
