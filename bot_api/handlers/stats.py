"""Handlers for statistics section."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from shared.database import (
    get_connection,
    get_or_create_user,
    get_user_groups,
    get_user_patterns,
    count_user_matches,
)

router = Router()


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        groups = await get_user_groups(db, user.id)
        patterns = await get_user_patterns(db, user.id)
        total_matches = await count_user_matches(db, user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])

    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        "📅 За всё время:\n"
        f"• Получено совпадений: <b>{total_matches}</b>\n"
        f"• Групп отслеживается: <b>{len(groups)}</b>\n"
        f"• Активных паттернов: <b>{len(patterns)}</b>",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()
