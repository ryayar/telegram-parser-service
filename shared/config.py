"""Application configuration via pydantic-settings.

Loads from .env file and environment variables.
Environment variables override .env values.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bot API (aiogram)
    bot_token: str = ""

    # Userbot (Telethon)
    api_id: int = 0
    api_hash: str = ""
    phone_number: str = ""

    # Database
    db_path: str = "data/database.db"

    # Logging
    log_level: str = "INFO"

    # Captcha
    captcha_window_minutes: int = 10
    admin_ids: list[int] = []

    # Duplicate grouping
    duplicate_window_minutes: int = 3

    # Logging output: "console" or "both" (console + file)
    log_output: str = "console"
    log_file_dir: str = "logs"

    @property
    def db_full_path(self) -> Path:
        path = Path(self.db_path)
        if not path.is_absolute():
            return BASE_DIR / path
        return path


settings = Settings()
