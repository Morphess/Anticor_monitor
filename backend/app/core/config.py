from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    APP_NAME: str
    DEBUG: bool
    DATABASE_URL: str
    SQL_ECHO: bool
    JWT_SECRET_KEY: str

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        # У .env є й змінні лише для docker compose (POSTGRES_*), застосунку вони не потрібні
        extra="ignore",
    )


settings = Settings()
