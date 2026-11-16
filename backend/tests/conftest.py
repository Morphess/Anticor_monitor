"""Налаштування тестів.

За замовчуванням тести працюють на тимчасовій базі SQLite — нічого встановлювати не потрібно.
Щоб прогнати їх на PostgreSQL (так робить CI), задайте окрему тестову базу:
    TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ac_test python -m pytest -q
УВАГА: тести перестворюють усі таблиці в цій базі.
"""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="ac-monitor-test-")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["AUTO_IMPORT"] = "0"
os.environ["DEMO_MODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture()
def db():
    """Чиста база із синтетичним набором організаторів і відкрита сесія."""
    from app.db import engine, session_scope
    from app.importer import import_dataset

    engine.dispose()
    import_dataset(reset=True)
    with session_scope() as s:
        yield s


@pytest.fixture()
def app_client():
    """Функція, що повертає браузер-клієнт, який увійшов як заданий користувач набору."""
    from fastapi.testclient import TestClient

    from app.importer import import_dataset
    from app.main import app

    import_dataset(reset=True)
    clients = []

    def login(user_id: str | None = None) -> TestClient:
        c = TestClient(app, follow_redirects=True)
        c.__enter__()
        clients.append(c)
        if user_id:
            assert c.post("/login", data={"user_id": user_id}).status_code == 200
        return c

    yield login
    for c in clients:
        c.__exit__(None, None, None)
