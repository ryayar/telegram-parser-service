"""Group detail handler — view and manage patterns active for a specific group."""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from shared.database import (
    get_connection,
    get_or_create_user,
    get_group_by_id,
    get_user_patterns,
    get_active_pattern_ids_for_group,
    add_pattern_to_group,
    remove_pattern_from_group,
    set_all_patterns_for_group,
    clear_all_patterns_for_group,
)
from shared.models import GroupStatus

router = Router()
logger = logging.getLogger(__name__)

STATUS_EMOJI = {"active": "✅", "pending": "⏳", "error": "❌", "left": "🚫"}


async def _group_detail_text_and_kb(
    user_id: int,
    group_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    async with get_connection() as db:
        group = await get_group_by_id(db, group_id)
        if not group:
            return "❌ Группа не найдена.", InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="groups")]
            ])

        all_patterns = await get_user_patterns(db, user_id)
        active_ids = await get_active_pattern_ids_for_group(db, user_id, group_id)

    status_emoji = STATUS_EMOJI.get(group.status.value, "")
    title = group.title or group.link

    lines = [f"📂 <b>{title}</b> {status_emoji}\n"]
    if all_patterns:
        lines.append("Слова, активные для этой группы:\n")
        for p in all_patterns:
            check = "✅" if p.id in active_ids else "☐"
            suffix = " <i>(умный)</i>" if p.pattern_type.value == "smart" else ""
            lines.append(f"{check} {p.value}{suffix}")
    else:
        lines.append("У вас нет добавленных слов.")

    text = "\n".join(lines)

    # Pattern toggle buttons (one per row)
    rows: list[list[InlineKeyboardButton]] = []
    for p in all_patterns:
        check = "✅" if p.id in active_ids else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{check} {p.value}",
            callback_data=f"gp_toggle:{group_id}:{p.id}",
        )])

    # Bulk actions
    if all_patterns:
        rows.append([
            InlineKeyboardButton(text="✅ Выбрать все", callback_data=f"gp_all:{group_id}"),
            InlineKeyboardButton(text="☐ Снять выбор", callback_data=f"gp_none:{group_id}"),
        ])

    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="groups")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("group_info:"))
async def cb_group_info(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)

    text, kb = await _group_detail_text_and_kb(user.id, group_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("gp_toggle:"))
async def cb_gp_toggle(callback: CallbackQuery):
    _, group_id_str, pattern_id_str = callback.data.split(":")
    group_id, pattern_id = int(group_id_str), int(pattern_id_str)

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        active_ids = await get_active_pattern_ids_for_group(db, user.id, group_id)

        if pattern_id in active_ids:
            await remove_pattern_from_group(db, user.id, pattern_id, group_id)
            logger.info("user=%d deactivated pattern=%d for group=%d", user.id, pattern_id, group_id)
        else:
            await add_pattern_to_group(db, user.id, pattern_id, group_id)
            logger.info("user=%d activated pattern=%d for group=%d", user.id, pattern_id, group_id)

    text, kb = await _group_detail_text_and_kb(user.id, group_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("gp_all:"))
async def cb_gp_all(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        await set_all_patterns_for_group(db, user.id, group_id)
        logger.info("user=%d selected ALL patterns for group=%d", user.id, group_id)

    text, kb = await _group_detail_text_and_kb(user.id, group_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("✅ Все слова выбраны")


@router.callback_query(F.data.startswith("gp_none:"))
async def cb_gp_none(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        await clear_all_patterns_for_group(db, user.id, group_id)
        logger.info("user=%d cleared ALL patterns for group=%d", user.id, group_id)

    text, kb = await _group_detail_text_and_kb(user.id, group_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("☐ Выбор снят")
