"""Captcha solving — handles emoji/text captchas after joining groups.

Detects captcha messages from bots in groups and attempts to solve them.
Currently supports:
- Emoji button captchas (click the matching emoji)
- Simple text button captchas (click the specified button)

Only processes captchas that are either:
- Explicitly mentioning the userbot account (message.mentioned)
- Arrived within CAPTCHA_WINDOW_MINUTES after the userbot joined the group
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from telethon import TelegramClient, events

from shared.config import settings
from userbot.state import recently_joined

logger = logging.getLogger(__name__)

# Patterns that indicate a captcha message
CAPTCHA_KEYWORDS = [
    "нажмите", "press", "click", "tap",
    "кнопку", "button",
    "подтвердите", "verify", "confirm",
    "не робот", "not a bot", "human",
    "капча", "captcha",
]

CAPTCHA_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in CAPTCHA_KEYWORDS),
    re.IGNORECASE,
)


def _recently_joined(chat_id: int) -> bool:
    """Return True if the userbot joined this chat within the configured window."""
    join_time = recently_joined.get(chat_id)
    if join_time is None:
        return False
    window = timedelta(minutes=settings.captcha_window_minutes)
    return datetime.utcnow() - join_time <= window


def register_handlers(client: TelegramClient) -> None:
    """Register captcha detection and solving handler."""

    @client.on(events.NewMessage())
    async def on_captcha_message(event: events.NewMessage.Event):
        if event.is_private or event.out:
            return

        message = event.message
        if not message.reply_markup:
            return

        text = message.text or message.raw_text or ""
        if not text:
            return

        # Check if message looks like a captcha
        if not CAPTCHA_PATTERN.search(text):
            return

        # Check if message is from a bot
        sender = await message.get_sender()
        if not sender or not getattr(sender, "bot", False):
            return

        # Core filter: only handle captchas directed at us
        mentioned = getattr(message, "mentioned", False)
        if not mentioned and not _recently_joined(event.chat_id):
            logger.debug(
                "Skipping captcha in chat %d — not mentioned and not recently joined",
                event.chat_id,
            )
            return

        sender_username = getattr(sender, "username", "") or ""
        logger.info(
            "Detected captcha in chat %d from bot @%s (mentioned=%s)",
            event.chat_id, sender_username, mentioned,
        )

        # Try to find and click the right button
        buttons = await message.get_buttons()
        if not buttons:
            return

        # Strategy 1: Single button → just click it
        flat_buttons = [btn for row in buttons for btn in row]
        if len(flat_buttons) == 1:
            try:
                await flat_buttons[0].click()
                logger.info("Clicked single captcha button in chat %d", event.chat_id)
                return
            except Exception as e:
                logger.error("Failed to click captcha button: %s", e)
                return

        # Strategy 2: Button text appears in the captcha message → click it
        for row in buttons:
            for btn in row:
                btn_text = btn.text or ""
                if btn_text and btn_text in text:
                    try:
                        await btn.click()
                        logger.info(
                            "Clicked matching captcha button '%s' in chat %d",
                            btn_text, event.chat_id,
                        )
                        return
                    except Exception as e:
                        logger.error("Failed to click captcha button '%s': %s", btn_text, e)

        # Strategy 3: Look for a "verify / I'm human" type button
        for row in buttons:
            for btn in row:
                btn_text = (btn.text or "").lower()
                if any(kw in btn_text for kw in ["verify", "подтвердить", "human", "не робот", "✅"]):
                    try:
                        await btn.click()
                        logger.info(
                            "Clicked verify button '%s' in chat %d",
                            btn.text, event.chat_id,
                        )
                        return
                    except Exception as e:
                        logger.error("Failed to click verify button: %s", e)

        logger.warning(
            "Could not solve captcha in chat %d (bot: @%s)",
            event.chat_id, sender_username,
        )
