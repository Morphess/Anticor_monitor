"""Підключення до PostgreSQL (SQLAlchemy 2 + psycopg 3) і сесія бази на час запиту.

Кожен HTTP-запит отримує власну сесію (див. middleware у main.py). Сервіси беруть її через session().
Операції процесу (подання, рішення тощо) самі фіксують свою транзакцію — див. services/workflow.py.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    # Час у базі зберігається в UTC; на київський переводиться під час показу
    connect_args={"check_same_thread": False} if _is_sqlite else {"options": "-c timezone=UTC"},
)

if _is_sqlite:  # SQLite не перевіряє зовнішні ключі без цього прагма
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
_current: ContextVar[Session | None] = ContextVar("db_session", default=None)


def session() -> Session:
    s = _current.get()
    if s is None:
        raise RuntimeError("Немає активної сесії бази: використовуйте session_scope()")
    return s


@contextmanager
def session_scope():
    """Відкриває сесію для запиту або скрипта. Незафіксовані зміни наприкінці фіксуються."""
    s = SessionLocal()
    token = _current.set(s)
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        _current.reset(token)
        s.close()


def init_db(drop: bool = False) -> None:
    from . import models  # noqa: F401 — реєструє таблиці

    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
