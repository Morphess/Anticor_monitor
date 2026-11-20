import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]

# Вибір середовища
DB_ENV = os.getenv("DB_ENV", "local").lower()

if DB_ENV not in ("local", "server"):
    raise ValueError("DB_ENV повинен бути 'local' або 'server'")


class Settings(BaseSettings):
    APP_NAME: str
    DEBUG: bool

    DATABASE_URL: str

    SQL_ECHO: bool
    JWT_SECRET_KEY: str
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT_SECONDS: int = Field(default=600, ge=30, le=3600)
    OLLAMA_NUM_PREDICT: int = Field(default=768, ge=1, le=4096)

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / f".env.{DB_ENV}",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
