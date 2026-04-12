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
    get_grouped_matches,
    mark_match_sent,
    mark_matches_sent_batch,
    get_group_by_id,
    _row_to_user,
)
from shared.models import Match, User

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5       # seconds between DB polls
SEND_DELAY = 0.05       # 50 ms between sends ≈ 20 msg/s (within Bot API limits)
PHOTO_TEXT_DELAY = 0.5  # delay between photo and text when sent separately
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
    pattern_value: str | None,
    groups: list[tuple[str, str | None]],  # list of (title, link)
) -> str:
    """Format notification text. groups is a list of (group_title, message_link)."""
    text = match.message_text
    if len(text) > MESSAGE_MAX_LEN:
        text = text[:MESSAGE_MAX_LEN] + "…"

    if pattern_value:
        parts: list[str] = [f"🔑 <b>Запрос:</b> {pattern_value}\n"]
    else:
        parts: list[str] = ["🔔 <b>Новое объявление!</b>\n"]

    if len(groups) == 1:
        title, link = groups[0]
        parts.append(f"📢 <b>Группа:</b> {title or 'Неизвестно'}")
        parts.append("")
        parts.append(text)
        if link:
            parts.append(f'\n🔗 <a href="{link}">Открыть сообщение</a>')
    else:
        parts.append(f"📢 <b>Найдено в {len(groups)} группах:</b>")
        for title, link in groups:
            label = title or "Неизвестно"
            if link:
                parts.append(f'  • <a href="{link}">{label}</a>')
            else:
                parts.append(f"  • {label}")
        parts.append("")
        parts.append(text)

    return "\n".join(parts)


async def _send_text(
    bot: Bot,
    telegram_id: int,
    text: str,
    silent: bool,
    media_path: str | None,
) -> None:
    """Send notification (with or without photo)."""
    import os
    if media_path and os.path.exists(media_path):
        if len(text) <= 1024:
            await bot.send_photo(
                chat_id=telegram_id,
                photo=FSInputFile(media_path),
                caption=text,
                parse_mode="HTML",
                disable_notification=silent,
            )
        else:
            await bot.send_photo(
                chat_id=telegram_id,
                photo=FSInputFile(media_path),
                disable_notification=silent,
            )
            await asyncio.sleep(PHOTO_TEXT_DELAY)
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
                disable_notification=silent,
                disable_web_page_preview=True,
            )
    else:
        if media_path:
            logger.warning("Media file missing: %s", media_path)
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode="HTML",
            disable_notification=silent,
            disable_web_page_preview=True,
        )


async def _process_match(
    bot: Bot,
    match: Match,
    already_sent: set[int],
) -> None:
    """Send notification for a match (possibly grouped with siblings)."""
    if match.id in already_sent:
        return

    async with get_connection() as db:
        row = await (await db.execute("SELECT * FROM users WHERE id = ?", (match.user_id,))).fetchone()
        if row is None:
            await mark_match_sent(db, match.id)
            already_sent.add(match.id)
            return

        user = _row_to_user(row)

        if not user.is_active:
            await mark_match_sent(db, match.id)
            already_sent.add(match.id)
            return

        pattern_value: str | None = None
        if match.pattern_id is not None:
            prow = await (
                await db.execute("SELECT value FROM patterns WHERE id = ?", (match.pattern_id,))
            ).fetchone()
            if prow:
                pattern_value = prow["value"]

        # Collect all sibling matches (same user + text hash, ready to send)
        if user.group_duplicates:
            siblings = await get_grouped_matches(db, match.user_id, match.text_hash)
        else:
            siblings = [match]

        # Build (title, link) list for each sibling
        groups: list[tuple[str, str | None]] = []
        sibling_ids: list[int] = []
        for sibling in siblings:
            if sibling.id in already_sent:
                continue
            g = await get_group_by_id(db, sibling.group_id)
            groups.append((g.title if g else "", sibling.message_link))
            sibling_ids.append(sibling.id)

    if not sibling_ids:
        return

    silent = _is_quiet_hours(user)
    text = _format_message(match, pattern_value, groups)
    media_path = match.media_path  # use photo from the first match

    try:
        await _send_text(bot, user.telegram_id, text, silent, media_path)

        async with get_connection() as db:
            await mark_matches_sent_batch(db, sibling_ids)
        already_sent.update(sibling_ids)

        logger.info(
            "match(es) %s → user %d (groups=%d, silent=%s)",
            sibling_ids, user.telegram_id, len(groups), silent,
        )

    except TelegramForbiddenError:
        logger.warning("User %d blocked the bot; discarding matches %s", user.telegram_id, sibling_ids)
        async with get_connection() as db:
            await mark_matches_sent_batch(db, sibling_ids)
        already_sent.update(sibling_ids)

    except TelegramBadRequest as exc:
        logger.error("Bad request for matches %s: %s; discarding", sibling_ids, exc)
        async with get_connection() as db:
            await mark_matches_sent_batch(db, sibling_ids)
        already_sent.update(sibling_ids)

    except Exception as exc:
        logger.error(
            "Transient error sending matches %s to user %d: %s",
            sibling_ids, user.telegram_id, exc,
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
                already_sent: set[int] = set()
                for match in matches:
                    await _process_match(bot, match, already_sent)
                    await asyncio.sleep(SEND_DELAY)

        except Exception as exc:
            logger.error("Sender loop iteration failed: %s", exc, exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)
