"""Userbot entry point — Telethon client for group monitoring.

Starts the Telethon client and runs:
- Message monitor (pattern matching on incoming messages)
- Group joiner (processes pending_joins queue)
- Captcha solver (handles captchas after joining)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telethon import TelegramClient

from shared.config import settings
from shared.database import init_db
from userbot import monitor, joiner, captcha

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).resolve().parent.parent / "sessions"


def create_client() -> TelegramClient:
    """Create and configure the Telethon client."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path = str(SESSION_DIR / "userbot")

    client = TelegramClient(
        session_path,
        api_id=settings.api_id,
        api_hash=settings.api_hash,
    )
    return client


async def main():
    logger.info("Initializing database...")
    await init_db()

    client = create_client()

    # Register event handlers
    monitor.register_handlers(client)
    captcha.register_handlers(client)

    logger.info("Starting userbot...")
    await client.start(phone=settings.phone_number or None)
    logger.info("Userbot started. Listening for messages...")

    # Start background joiner loop
    asyncio.create_task(joiner.joiner_loop(client))

    # Run until disconnected
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
