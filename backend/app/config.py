"""Налаштування застосунку (змінні оточення або файл .env у корені репозиторію)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]          # корінь репозиторію
FRONTEND_DIR = ROOT_DIR / "frontend"
DATASET_DIR = ROOT_DIR / "data" / "nabir-orhanizatoriv"  # синтетичний набір організаторів


def _load_env_file() -> None:
    env = ROOT_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip():  # порожнє значення = значення за замовчуванням
                os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

# PostgreSQL: postgresql+psycopg://користувач:пароль@хост:порт/база
# Для швидкої перевірки без PostgreSQL: sqlite:///./ac_monitor.db
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/ac_monitor")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(ROOT_DIR / "uploads")))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "10"))
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".txt", ".jpg", ".jpeg", ".png", ".zip"}
# 1 — якщо база порожня, імпортувати синтетичний набір організаторів
AUTO_IMPORT = os.getenv("AUTO_IMPORT", "1") == "1"
# 1 — демонстраційний вхід: вибір користувача зі списку без пароля (у наборі лише ролі й посади).
# 0 — вхід за логіном і паролем, який задає адміністратор.
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"
# 1 — брати IP із заголовка X-Forwarded-For (якщо застосунок за nginx/проксі)
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
TIMEZONE = "Europe/Kyiv"
