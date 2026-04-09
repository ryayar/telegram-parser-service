"""Handler for browsing match history with pagination."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from shared.database import (
    get_connection,
    get_or_create_user,
    get_user_matches,
    count_user_matches,
    get_group_by_id,
)

router = Router()

PAGE_SIZE = 5


async def _build_history_text_and_kb(
    user_id: int,
    offset: int,
) -> tuple[str, InlineKeyboardMarkup]:
    async with get_connection() as db:
        total = await count_user_matches(db, user_id)

        if total == 0:
            text = "📋 <b>История совпадений</b>\n\nПока ничего не найдено."
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
            ])
            return text, kb

        matches = await get_user_matches(db, user_id, limit=PAGE_SIZE, offset=offset)

        # Fetch group titles and pattern values in one pass
        group_cache: dict[int, str] = {}
        pattern_cache: dict[int, str] = {}

        for m in matches:
            if m.group_id not in group_cache:
                g = await get_group_by_id(db, m.group_id)
                group_cache[m.group_id] = g.title or g.link if g else "?"

            if m.pattern_id is not None and m.pattern_id not in pattern_cache:
                row = await (
                    await db.execute(
                        "SELECT value FROM patterns WHERE id = ?", (m.pattern_id,)
                    )
                ).fetchone()
                pattern_cache[m.pattern_id] = row["value"] if row else "удалён"

    page = offset // PAGE_SIZE + 1
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    lines = [f"📋 <b>История совпадений</b>  (стр. {page}/{total_pages})\n"]

    for m in matches:
        group_title = group_cache.get(m.group_id, "?")
        pattern_val = pattern_cache.get(m.pattern_id, "") if m.pattern_id else ""

        # Compact preview: first 120 chars of message
        preview = m.message_text.replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:120] + "…"

        dt = m.created_at.strftime("%d %b %H:%M")

        header = f"📢 {group_title}"
        if pattern_val:
            header += f"  •  🔑 {pattern_val}"
        lines.append(f"\n<b>{header}</b>")
        lines.append(preview)

        footer = f"🕐 {dt}"
        if m.message_link:
            footer += f'  •  <a href="{m.message_link}">Открыть</a>'
        lines.append(footer)

    text = "\n".join(lines)

    # Navigation row
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"history:{offset - PAGE_SIZE}"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"history:{offset + PAGE_SIZE}"))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ] if nav else [
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])

    return text, kb


@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)

    text, kb = await _build_history_text_and_kb(user.id, offset=0)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML",
                                     disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(F.data.startswith("history:"))
async def cb_history_page(callback: CallbackQuery):
    offset = int(callback.data.split(":")[1])

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)

    text, kb = await _build_history_text_and_kb(user.id, offset=offset)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML",
                                     disable_web_page_preview=True)
    await callback.answer()
