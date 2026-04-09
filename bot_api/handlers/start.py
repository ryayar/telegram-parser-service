"""Start command and main menu handler."""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from shared.database import get_connection, get_or_create_user, update_user
from bot_api.keyboards.main_menu import get_main_menu_kb

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "📋 <b>Telegram Parser</b>\n\n"
    "Добро пожаловать! Выберите действие:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with get_connection() as db:
        user = await get_or_create_user(db, message.from_user.id)
    logger.info("user=%d /start (active=%s)", message.from_user.id, user.is_active)
    await message.answer(
        WELCOME_TEXT,
        reply_markup=get_main_menu_kb(user.is_active),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=get_main_menu_kb(user.is_active),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_pause")
async def cb_toggle_pause(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        new_active = not user.is_active
        await update_user(db, user.id, is_active=int(new_active))

    logger.info(
        "user=%d toggled monitoring: %s",
        callback.from_user.id,
        "resumed" if new_active else "paused",
    )
    status = "▶️ Мониторинг возобновлён" if new_active else "⏸ Мониторинг приостановлен"
    await callback.answer(status)
    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=get_main_menu_kb(new_active),
        parse_mode="HTML",
    )
