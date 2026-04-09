"""Shared logging configuration for bot_api and userbot."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from shared.config import settings

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
BACKUP_COUNT = 5               # keep last 5 rotated files


def setup_logging(service_name: str) -> None:
    """Configure logging for the given service.

    service_name: "bot" or "userbot" — used as the log filename.
    Reads LOG_LEVEL and LOG_OUTPUT from settings.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT)

    # Console handler — always on
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler — only when LOG_OUTPUT=both
    if settings.log_output.lower() == "both":
        log_dir = Path(settings.log_file_dir)
        if not log_dir.is_absolute():
            from shared.config import BASE_DIR
            log_dir = BASE_DIR / log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / f"{service_name}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        logging.getLogger(__name__).info(
            "Logging to console + file: %s", log_path
        )
