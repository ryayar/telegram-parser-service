"""Background process for polling unsent matches and delivering notifications."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from datetime import time as dt_time

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import FSInputFile

from shared.database import (
    get_connection,
    get_unsent_matches,
    mark_match_sent,
    get_group_by_id,
    _row_to_user,
)
from shared.models import Match, User

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5       # seconds between DB polls
SEND_DELAY = 0.05       # 50 ms between sends ≈ 20 msg/s (within Bot API limits)
MESSAGE_MAX_LEN = 1000  # truncate long messages to this length


def _is_quiet_hours(user: User) -> bool:
    """Return True if current local time falls within the user's quiet hours."""
    if not user.quiet_hours_start or not user.quiet_hours_end:
        return False
    try:
        start = dt_time.fromisoformat(user.quiet_hours_start)
        end = dt_time.fromisoformat(user.quiet_hours_end)
    except ValueError:
        return False

    tz_offset = timedelta(hours=user.timezone)
    current = (datetime.utcnow() + tz_offset).time()

    if start <= end:
        # Same-day window (e.g. 02:00 – 08:00)
        return start <= current < end
    else:
        # Overnight window (e.g. 23:00 – 08:00)
        return current >= start or current < end


def _format_message(
    match: Match,
    group_title: str,
    pattern_value: str | None,
) -> str:
    text = match.message_text
    if len(text) > MESSAGE_MAX_LEN:
        text = text[:MESSAGE_MAX_LEN] + "…"

    parts: list[str] = ["🔔 <b>Новое объявление!</b>\n"]
    parts.append(f"📢 <b>Группа:</b> {group_title or 'Неизвестно'}")
    if pattern_value:
        parts.append(f"🔑 <b>Запрос:</b> {pattern_value}")
    parts.append("")
    parts.append(text)
    if match.message_link:
        parts.append(f'\n🔗 <a href="{match.message_link}">Открыть сообщение</a>')

    return "\n".join(parts)


async def _process_match(bot: Bot, match: Match) -> None:
    """Send one match notification; mark it sent regardless of delivery outcome."""
    async with get_connection() as db:
        row = await (await db.execute("SELECT * FROM users WHERE id = ?", (match.user_id,))).fetchone()
        if row is None:
            # User was deleted — discard the match
            await mark_match_sent(db, match.id)
            return

        user = _row_to_user(row)

        # User paused monitoring — discard silently so the backlog doesn't grow
        if not user.is_active:
            await mark_match_sent(db, match.id)
            return

        group = await get_group_by_id(db, match.group_id)
        group_title = group.title if group else ""

        pattern_value: str | None = None
        if match.pattern_id is not None:
            prow = await (
                await db.execute("SELECT value FROM patterns WHERE id = ?", (match.pattern_id,))
            ).fetchone()
            if prow:
                pattern_value = prow["value"]

    silent = _is_quiet_hours(user)
    text = _format_message(match, group_title, pattern_value)

    try:
        if match.media_path:
            import os
            if os.path.exists(match.media_path):
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=FSInputFile(match.media_path),
                    caption=text,
                    parse_mode="HTML",
                    disable_notification=silent,
                )
            else:
                # File missing — fall back to text only
                logger.warning("Media file missing for match #%d: %s", match.id, match.media_path)
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    parse_mode="HTML",
                    disable_notification=silent,
                    disable_web_page_preview=True,
                )
        else:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="HTML",
                disable_notification=silent,
                disable_web_page_preview=True,
            )
        async with get_connection() as db:
            await mark_match_sent(db, match.id)
        logger.info(
            "match #%d → user %d (silent=%s, photo=%s)",
            match.id, user.telegram_id, silent, bool(match.media_path),
        )

    except TelegramForbiddenError:
        # User blocked the bot — mark sent so we never retry
        logger.warning(
            "User %d blocked the bot; discarding match #%d", user.telegram_id, match.id
        )
        async with get_connection() as db:
            await mark_match_sent(db, match.id)

    except TelegramBadRequest as exc:
        logger.error("Bad request for match #%d: %s; discarding", match.id, exc)
        async with get_connection() as db:
            await mark_match_sent(db, match.id)

    except Exception as exc:
        # Transient error — do NOT mark sent; will retry on next poll
        logger.error(
            "Transient error sending match #%d to user %d: %s",
            match.id, user.telegram_id, exc,
        )


async def sender_loop(bot: Bot) -> None:
    """Infinite background loop: poll unsent matches and deliver notifications."""
    logger.info("Sender loop started (poll every %ds)", POLL_INTERVAL)
    while True:
        try:
            async with get_connection() as db:
                matches = await get_unsent_matches(db, limit=50)

            if matches:
                logger.debug("Processing %d unsent match(es)", len(matches))
                for match in matches:
                    await _process_match(bot, match)
                    await asyncio.sleep(SEND_DELAY)

        except Exception as exc:
            logger.error("Sender loop iteration failed: %s", exc, exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)
