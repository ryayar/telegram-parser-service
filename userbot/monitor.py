"""Incoming message handler — monitors all groups.

Listens to all new messages in chats where the userbot is present.
For each message:
1. Find the group in DB by Telegram chat ID
2. Find which users are subscribed to this group
3. For each user, check their patterns against the message text
4. If matched and not a duplicate, write to matches table
"""
from __future__ import annotations

import logging
import os

from telethon import TelegramClient, events

from shared.database import (
    get_connection,
    get_group_by_telegram_id,
    get_users_for_telegram_group,
    get_patterns_for_user_in_group,
    check_duplicate,
    create_match,
    update_match_media,
)
from userbot.matcher import compute_text_hash, find_matching_patterns

logger = logging.getLogger(__name__)


def register_handlers(client: TelegramClient) -> None:
    """Register the message monitoring event handler on the client."""

    @client.on(events.NewMessage())
    async def on_new_message(event: events.NewMessage.Event):
        # Skip messages from ourselves and private chats
        if event.is_private or event.out:
            return

        message = event.message
        # raw_text returns plain text without markdown markers (**bold**, etc.)
        # message.text may include markdown formatting from Telethon entity rendering
        text = message.raw_text or message.text or ""
        has_photo = message.photo is not None
        if not text and not has_photo:
            return
        if not has_photo and len(text) < 2:
            return

        chat_id = event.chat_id
        text_hash = compute_text_hash(text)

        # Build message link
        message_link = None
        try:
            chat = await event.get_chat()
            if hasattr(chat, "username") and chat.username:
                # Public group — normal link
                message_link = f"https://t.me/{chat.username}/{message.id}"
            else:
                # Private group — use internal link (only works for members)
                # chat_id from Telethon is already negative (-100xxxxxxxxx)
                # t.me/c/ expects the bare channel id without -100 prefix
                bare_id = abs(chat_id)
                if str(bare_id).startswith("100"):
                    bare_id = int(str(bare_id)[3:])
                message_link = f"https://t.me/c/{bare_id}/{message.id}"
        except Exception:
            pass

        # Collect created match IDs for photo download (done outside the DB context)
        created_matches: list[tuple[int, int]] = []  # (match_id, group_db_id)

        async with get_connection() as db:
            # Resolve group in our DB (normalize peer id formats)
            group = await get_group_by_telegram_id(db, chat_id)
            if not group and chat_id < 0:
                # If DB stored channel_id (positive), map -100xxxxxxxxxx -> x
                alt_id = abs(chat_id) - 1000000000000
                if alt_id > 0:
                    group = await get_group_by_telegram_id(db, alt_id)
            if not group:
                return

            # Find all active users subscribed to this group
            users = await get_users_for_telegram_group(db, chat_id)
            if not users:
                return

            for user in users:
                # Get only patterns the user has activated for this group
                patterns = await get_patterns_for_user_in_group(db, user.id, chat_id)
                if not patterns:
                    continue

                # Check which patterns match
                matched = find_matching_patterns(text, patterns)
                if not matched:
                    continue

                # Deduplication
                is_dup = await check_duplicate(db, user.id, text_hash, hours=2)
                if is_dup:
                    logger.debug(
                        "Duplicate for user %d, hash=%s", user.telegram_id, text_hash[:8]
                    )
                    continue

                # Write match for the first matched pattern
                first_pattern = matched[0]
                match = await create_match(
                    db,
                    user_id=user.id,
                    group_id=group.id,
                    message_text=text[:4000],
                    text_hash=text_hash,
                    pattern_id=first_pattern.id,
                    message_link=message_link,
                )
                logger.info(
                    "Match for user %d: pattern='%s' in chat %d",
                    user.telegram_id,
                    first_pattern.value,
                    chat_id,
                )
                if has_photo:
                    created_matches.append((match.id, group.id))

        # Download photo outside the DB context to avoid holding the connection
        if has_photo and created_matches:
            try:
                from shared.config import settings
                media_dir = str(settings.db_full_path.parent / "media")
                os.makedirs(media_dir, exist_ok=True)
                filename = f"{created_matches[0][1]}_{message.id}.jpg"
                media_path = os.path.join(media_dir, filename)
                await client.download_media(message.photo, file=media_path)
                logger.info("Downloaded photo → %s", media_path)
                async with get_connection() as db:
                    for match_id, _ in created_matches:
                        await update_match_media(db, match_id, media_path)
            except Exception as exc:
                logger.warning("Failed to download photo for message %d: %s", message.id, exc)
