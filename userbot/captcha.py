"""Captcha solving — handles emoji/text captchas after joining groups.

Detects captcha messages from bots in groups and attempts to solve them.
Currently supports:
- Emoji button captchas (click the matching emoji)
- Simple text button captchas (click the specified button)
- Math captchas (e.g. "3 + 5 = ?", "три плюс пять", "сколько будет 3*5")

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
    "сколько будет", "сколько равно", "ответ", "решите",
    "how much", "what is", "solve",
]

CAPTCHA_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in CAPTCHA_KEYWORDS),
    re.IGNORECASE,
)

# ─── Math Captcha ────────────────────────────────────────────────────

# Number words → int (Russian + English)
_NUMBER_WORDS: dict[str, int] = {
    # Russian
    "ноль": 0, "нуль": 0,
    "один": 1, "одна": 1,
    "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12,
    "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20,
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

# Operation words → operator symbol
_OP_WORDS: dict[str, str] = {
    # Russian
    "плюс": "+", "минус": "-",
    "умножить": "*", "умножено": "*", "умножить на": "*",
    "разделить": "/", "разделить на": "/", "разделено": "/",
    # English
    "plus": "+", "minus": "-", "add": "+",
    "multiply": "*", "times": "*",
    "divide": "/", "divided": "/",
}

# Symbols
_OP_SYMBOLS: dict[str, str] = {
    "+": "+", "-": "-",
    "*": "*", "×": "*", "x": "*", "х": "*",  # latin x and cyrillic х
    "/": "/", "÷": "/",
}

# Regex to detect math expressions in text
_MATH_KEYWORDS = re.compile(
    r"\b(плюс|минус|умнож|раздел|plus|minus|times|divide|multiply"
    r"|\d+\s*[+\-*/×÷]\s*\d+)\b"
    r"|сколько будет",
    re.IGNORECASE,
)


def _solve_math_captcha(text: str) -> int | None:
    """Try to extract and evaluate a math expression from captcha text.

    Returns the integer result or None if no math expression found.
    Supports: digits, number words (RU/EN), operator words/symbols.
    """
    text_lower = text.lower()

    # Normalize operator words (longest first to avoid partial matches)
    expr = text_lower
    for word in sorted(_OP_WORDS, key=len, reverse=True):
        expr = re.sub(r"\b" + re.escape(word) + r"\b", " " + _OP_WORDS[word] + " ", expr)

    # Normalize number words (longest first)
    for word in sorted(_NUMBER_WORDS, key=len, reverse=True):
        expr = re.sub(r"\b" + re.escape(word) + r"\b", str(_NUMBER_WORDS[word]), expr)

    # Normalize operator symbols (×, ÷, cyrillic х)
    for sym, op in _OP_SYMBOLS.items():
        expr = expr.replace(sym, op)

    # Extract the first valid math expression: number op number
    match = re.search(r"(\d+)\s*([+\-*/])\s*(\d+)", expr)
    if not match:
        return None

    a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/" and b != 0:
        result = a / b
        return int(result) if result == int(result) else None
    return None


async def _notify_admins(
    client: TelegramClient,
    chat_id: int,
    bot_username: str,
    captcha_text: str,
) -> None:
    """Send a notification to all configured admins about an unsolved captcha."""
    if not settings.admin_ids:
        return

    preview = captcha_text[:300] + ("…" if len(captcha_text) > 300 else "")
    msg = (
        f"⚠️ Не удалось решить капчу!\n\n"
        f"Чат: <code>{chat_id}</code>\n"
        f"Бот: @{bot_username}\n\n"
        f"Текст капчи:\n<blockquote>{preview}</blockquote>\n\n"
        f"Пожалуйста, вступите в чат вручную и пройдите капчу."
    )

    for admin_id in settings.admin_ids:
        try:
            await client.send_message(admin_id, msg, parse_mode="html")
            logger.info("Notified admin %d about unsolved captcha in chat %d", admin_id, chat_id)
        except Exception as e:
            logger.error("Failed to notify admin %d: %s", admin_id, e)


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
        # Skip if this looks like a math captcha — numbers in text would cause false matches
        is_math = bool(_MATH_KEYWORDS.search(text))
        if not is_math:
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

        # Strategy 4: Math captcha — evaluate expression, click button with result
        if is_math:
            answer = _solve_math_captcha(text)
            if answer is not None:
                logger.info(
                    "Math captcha in chat %d — computed answer: %d",
                    event.chat_id, answer,
                )
                for row in buttons:
                    for btn in row:
                        btn_text = (btn.text or "").strip()
                        # Match button text as integer or with = sign (e.g. "= 8", "8")
                        cleaned = re.sub(r"[^0-9\-]", "", btn_text)
                        if cleaned and int(cleaned) == answer:
                            try:
                                await btn.click()
                                logger.info(
                                    "Clicked math captcha button '%s' (answer=%d) in chat %d",
                                    btn_text, answer, event.chat_id,
                                )
                                return
                            except Exception as e:
                                logger.error(
                                    "Failed to click math captcha button '%s': %s",
                                    btn_text, e,
                                )
            else:
                logger.warning(
                    "Math captcha detected in chat %d but could not evaluate expression: %r",
                    event.chat_id, text[:200],
                )

        logger.warning(
            "Could not solve captcha in chat %d (bot: @%s)",
            event.chat_id, sender_username,
        )
        await _notify_admins(client, event.chat_id, sender_username, text)
