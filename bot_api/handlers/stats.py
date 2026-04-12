"""Handlers for statistics section."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from shared.config import settings
from shared.database import (
    get_connection,
    get_or_create_user,
    get_user_groups,
    get_user_patterns,
    count_user_matches,
    get_click_stats,
    get_total_clicks,
)

router = Router()


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery):
    is_admin = callback.from_user.id in settings.admin_ids

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        groups = await get_user_groups(db, user.id)
        patterns = await get_user_patterns(db, user.id)
        total_matches = await count_user_matches(db, user.id)

    rows = [[InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]]
    if is_admin:
        rows.insert(0, [InlineKeyboardButton(text="📈 Статистика переходов", callback_data="admin_click_stats")])

    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        "📅 За всё время:\n"
        f"• Получено совпадений: <b>{total_matches}</b>\n"
        f"• Групп отслеживается: <b>{len(groups)}</b>\n"
        f"• Активных паттернов: <b>{len(patterns)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_click_stats")
async def cb_admin_click_stats(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    async with get_connection() as db:
        stats_30 = await get_click_stats(db, days=30, limit=15)
        total_30 = await get_total_clicks(db, days=30)
        total_7 = await get_total_clicks(db, days=7)

    lines = ["📈 <b>Статистика переходов</b>\n"]
    lines.append(f"За 7 дней: <b>{total_7}</b> кликов")
    lines.append(f"За 30 дней: <b>{total_30}</b> кликов\n")

    if stats_30:
        lines.append("<b>Топ групп по переходам (30 дней):</b>")
        for i, row in enumerate(stats_30, 1):
            title = row["title"] or row["link"] or "?"
            clicks = row["clicks"]
            lines.append(f"{i}. {title[:40]} — <b>{clicks}</b>")
    else:
        lines.append("Переходов пока нет.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="stats")],
    ])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()
