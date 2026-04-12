"""Handlers for user settings (timezone, quiet hours)."""
from __future__ import annotations

import logging
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from shared.database import get_connection, get_or_create_user, update_user
from bot_api.keyboards.settings import get_timezone_kb, get_quiet_hours_kb
from bot_api.states.user_states import SettingsState

router = Router()
logger = logging.getLogger(__name__)

QUIET_HOURS_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*[-\u2013\u2014]\s*(\d{1,2}):(\d{2})$")


def _tz_label(offset: int) -> str:
    sign = "+" if offset >= 0 else ""
    return f"UTC{sign}{offset}"


def _settings_kb(user) -> "InlineKeyboardMarkup":
    from bot_api.keyboards.settings import get_settings_kb
    return get_settings_kb(user.new_group_patterns, user.new_pattern_groups, user.group_duplicates)


def _settings_text(tz: str, qh: str) -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"🌍 Часовой пояс: <b>{tz}</b>\n"
        f"🔕 Тихие часы: <b>{qh}</b>"
    )


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)

    tz = _tz_label(user.timezone)
    qh = f"{user.quiet_hours_start} — {user.quiet_hours_end}" if user.quiet_hours_start else "отключены"

    await callback.message.edit_text(
        _settings_text(tz, qh),
        reply_markup=_settings_kb(user),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Auto-activate toggles ───────────────────────────────────────────


@router.callback_query(F.data == "toggle_new_group_patterns")
async def cb_toggle_new_group_patterns(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        new_val = not user.new_group_patterns
        await update_user(db, user.id, new_group_patterns=int(new_val))

    logger.info("user=%d set new_group_patterns=%s", callback.from_user.id, new_val)
    status = "✅ Включено" if new_val else "☐ Выключено"
    await callback.answer(f"Новая группа — все слова: {status}")

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
    tz = _tz_label(user.timezone)
    qh = f"{user.quiet_hours_start} — {user.quiet_hours_end}" if user.quiet_hours_start else "отключены"
    await callback.message.edit_text(
        _settings_text(tz, qh),
        reply_markup=_settings_kb(user),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "toggle_group_duplicates")
async def cb_toggle_group_duplicates(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        new_val = not user.group_duplicates
        await update_user(db, user.id, group_duplicates=int(new_val))

    logger.info("user=%d set group_duplicates=%s", callback.from_user.id, new_val)
    status = "✅ Включено" if new_val else "☐ Выключено"
    await callback.answer(f"Группировка дублей: {status}")

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
    tz = _tz_label(user.timezone)
    qh = f"{user.quiet_hours_start} — {user.quiet_hours_end}" if user.quiet_hours_start else "отключены"
    await callback.message.edit_text(
        _settings_text(tz, qh),
        reply_markup=_settings_kb(user),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "toggle_new_pattern_groups")
async def cb_toggle_new_pattern_groups(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        new_val = not user.new_pattern_groups
        await update_user(db, user.id, new_pattern_groups=int(new_val))

    logger.info("user=%d set new_pattern_groups=%s", callback.from_user.id, new_val)
    status = "✅ Включено" if new_val else "☐ Выключено"
    await callback.answer(f"Новое слово — все группы: {status}")

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
    tz = _tz_label(user.timezone)
    qh = f"{user.quiet_hours_start} — {user.quiet_hours_end}" if user.quiet_hours_start else "отключены"
    await callback.message.edit_text(
        _settings_text(tz, qh),
        reply_markup=_settings_kb(user),
        parse_mode="HTML",
    )


# ─── Timezone ────────────────────────────────────────────────────────


@router.callback_query(F.data == "settings_timezone")
async def cb_settings_timezone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsState.waiting_for_timezone)
    await callback.message.edit_text(
        "Выберите часовой пояс:\n\n"
        "Или отправьте число от -12 до +14.\n\n"
        "Часовой пояс нужен, чтобы уведомления и «тихие часы» работали по вашему местному времени.\n\n"
        "Если выбрать правильный пояс, бот будет присылать совпадения в тихие часы без звука.",
        reply_markup=get_timezone_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tz:"))
async def cb_tz_selected(callback: CallbackQuery, state: FSMContext):
    offset = int(callback.data.split(":")[1])
    await state.clear()

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        await update_user(db, user.id, timezone=offset)

    logger.info("user=%d set timezone=%s", callback.from_user.id, _tz_label(offset))
    await callback.answer(f"✅ Часовой пояс: {_tz_label(offset)}")

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)

    tz = _tz_label(user.timezone)
    qh = f"{user.quiet_hours_start} — {user.quiet_hours_end}" if user.quiet_hours_start else "отключены"

    await callback.message.edit_text(
        _settings_text(tz, qh),
        reply_markup=_settings_kb(user),
        parse_mode="HTML",
    )


@router.message(SettingsState.waiting_for_timezone)
async def msg_timezone(message: Message, state: FSMContext):
    text = (message.text or "").strip().lstrip("+")
    try:
        offset = int(text)
    except ValueError:
        await message.answer("❌ Отправьте число от -12 до +14")
        return

    if not (-12 <= offset <= 14):
        await message.answer("❌ Часовой пояс должен быть от -12 до +14")
        return

    await state.clear()

    async with get_connection() as db:
        user = await get_or_create_user(db, message.from_user.id)
        await update_user(db, user.id, timezone=offset)

    logger.info("user=%d set timezone=%s (text input)", message.from_user.id, _tz_label(offset))
    await message.answer(
        f"✅ Часовой пояс установлен: <b>{_tz_label(offset)}</b>",
        parse_mode="HTML",
    )


# ─── Quiet Hours ─────────────────────────────────────────────────────


@router.callback_query(F.data == "settings_quiet_hours")
async def cb_settings_quiet_hours(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsState.waiting_for_quiet_hours)
    await callback.message.edit_text(
        "Отправьте тихие часы в формате:\n\n"
        "<b>ЧЧ:ММ-ЧЧ:ММ</b>\n\n"
        "Примеры:\n"
        "• 23:00-08:00\n"
        "• 22:30-07:00\n"
        "• 00:00-09:00\n\n"
        "В это время уведомления будут приходить без звука.",
        reply_markup=get_quiet_hours_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "quiet_hours_off")
async def cb_quiet_hours_off(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        await update_user(db, user.id, quiet_hours_start=None, quiet_hours_end=None)
    logger.info("user=%d disabled quiet hours", callback.from_user.id)
    await callback.answer("✅ Тихие часы отключены")

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)

    tz = _tz_label(user.timezone)
    await callback.message.edit_text(
        _settings_text(tz, "отключены"),
        reply_markup=_settings_kb(user),
        parse_mode="HTML",
    )


@router.message(SettingsState.waiting_for_quiet_hours)
async def msg_quiet_hours(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    match = QUIET_HOURS_RE.match(text)

    if not match:
        await message.answer(
            "❌ Неверный формат. Отправьте в формате ЧЧ:ММ-ЧЧ:ММ\n"
            "Пример: 23:00-08:00",
        )
        return

    h1, m1, h2, m2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
    if not (0 <= h1 <= 23 and 0 <= m1 <= 59 and 0 <= h2 <= 23 and 0 <= m2 <= 59):
        await message.answer("❌ Некорректное время.")
        return

    start = f"{h1:02d}:{m1:02d}"
    end = f"{h2:02d}:{m2:02d}"
    await state.clear()

    async with get_connection() as db:
        user = await get_or_create_user(db, message.from_user.id)
        await update_user(db, user.id, quiet_hours_start=start, quiet_hours_end=end)

    logger.info("user=%d set quiet hours %s—%s", message.from_user.id, start, end)
    await message.answer(
        f"✅ Тихие часы установлены: <b>{start} — {end}</b>",
        parse_mode="HTML",
    )
