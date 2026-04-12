"""Bot API entry point — aiogram bot for user interaction."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message

from shared.config import settings
from shared.database import init_db
from shared.logging_setup import setup_logging

from bot_api.fsm_storage import SQLiteStorage
from bot_api.handlers import start, groups, patterns, settings as settings_handler, stats, history, group_detail, clicks
from bot_api.sender import sender_loop


setup_logging("bot")
logger = logging.getLogger(__name__)


def _make_fallback_router() -> Router:
    """Fallback router — included last so it only fires when nothing else matched."""
    router = Router(name="fallback")

    @router.message()
    async def fallback_handler(message: Message):
        from shared.database import get_connection, get_or_create_user
        from bot_api.keyboards.main_menu import get_main_menu_kb

        logger.debug(
            "fallback triggered for user=%d text=%r",
            message.from_user.id,
            (message.text or "")[:80],
        )
        async with get_connection() as db:
            user = await get_or_create_user(db, message.from_user.id)
        await message.answer(
            start.WELCOME_TEXT,
            reply_markup=get_main_menu_kb(user.is_active),
            parse_mode="HTML",
        )

    return router


def create_dispatcher() -> Dispatcher:
    storage = SQLiteStorage(str(settings.db_full_path))
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(groups.router)
    dp.include_router(group_detail.router)
    dp.include_router(patterns.router)
    dp.include_router(settings_handler.router)
    dp.include_router(stats.router)
    dp.include_router(clicks.router)
    dp.include_router(history.router)
    dp.include_router(_make_fallback_router())  # must be last

    return dp


async def main():
    logger.info("Initializing database...")
    await init_db()

    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Starting bot...")
    asyncio.create_task(sender_loop(bot))
    await dp.start_polling(bot)


def create_bot() -> Bot:
    return Bot(token=settings.bot_token)


if __name__ == "__main__":
    asyncio.run(main())
