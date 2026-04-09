"""Handlers for groups management."""
from __future__ import annotations

import logging
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from shared.database import (
    get_connection,
    get_or_create_user,
    get_user_groups,
    create_group,
    get_group_by_link,
    add_user_to_group,
    remove_user_from_group,
    create_pending_join,
    set_all_patterns_for_group,
)
from bot_api.keyboards.groups import (
    get_groups_list_kb,
    get_group_delete_kb,
    get_group_added_kb,
    get_cancel_kb,
)
from bot_api.states.user_states import AddGroupState

router = Router()
logger = logging.getLogger(__name__)

LINK_PATTERN = re.compile(
    r"(https?://t\.me/[\w+]+|@[\w]+)",
    re.IGNORECASE,
)

STATUS_EMOJI = {"active": "✅", "pending": "⏳", "error": "❌", "left": "🚫"}


@router.callback_query(F.data == "groups")
async def cb_groups_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        groups = await get_user_groups(db, user.id)

    if groups:
        lines = ["📂 <b>Мои группы</b>\n"]
        for i, g in enumerate(groups, 1):
            emoji = STATUS_EMOJI.get(g.status.value, "")
            lines.append(f"{i}. {g.title or g.link} {emoji}")
        text = "\n".join(lines)
    else:
        text = "📂 <b>Мои группы</b>\n\nСписок пуст. Добавьте первую группу!"

    await callback.message.edit_text(
        text,
        reply_markup=get_groups_list_kb(groups),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "group_add")
async def cb_group_add(callback: CallbackQuery, state: FSMContext):
    logger.info("user=%d opened add-group dialog", callback.from_user.id)
    await state.set_state(AddGroupState.waiting_for_link)
    await callback.message.edit_text(
        "Отправьте ссылку на группу:\n\n"
        "Примеры:\n"
        "• https://t.me/baraholka_msk\n"
        "• https://t.me/+AbCdEfGhIjK\n"
        "• @group_username",
        reply_markup=get_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddGroupState.waiting_for_link)
async def msg_group_link(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    logger.info("user=%d sent group link candidate: %r", message.from_user.id, text)

    match = LINK_PATTERN.search(text)

    if not match:
        logger.warning("user=%d bad link format: %r", message.from_user.id, text)
        await message.answer(
            "❌ Неверный формат. Отправьте ссылку вида:\n"
            "https://t.me/group или @group_username",
            reply_markup=get_cancel_kb(),
        )
        return

    link = match.group(1)
    logger.info("user=%d parsed link: %s", message.from_user.id, link)
    await state.clear()

    async with get_connection() as db:
        user = await get_or_create_user(db, message.from_user.id)

        group = await get_group_by_link(db, link)
        if group is None:
            group = await create_group(db, link=link)
            await create_pending_join(db, link)
            logger.info("user=%d created new group id=%d link=%s, pending_join queued", message.from_user.id, group.id, link)
        else:
            logger.info("user=%d group id=%d link=%s already exists (status=%s), re-linking", message.from_user.id, group.id, link, group.status.value)

        await add_user_to_group(db, user.id, group.id)
        await set_all_patterns_for_group(db, user.id, group.id)
        logger.info("user=%d linked to group id=%d, all patterns activated", message.from_user.id, group.id)

    await message.answer(
        "✅ <b>Группа добавлена в очередь!</b>\n\n"
        "Бот попытается вступить в группу.\n"
        "Статус можно посмотреть в разделе «Группы».",
        reply_markup=get_group_added_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "group_delete_select")
async def cb_group_delete_select(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        groups = await get_user_groups(db, user.id)

    if not groups:
        await callback.answer("Нет групп для удаления")
        return

    await callback.message.edit_text(
        "Выберите группу для удаления:",
        reply_markup=get_group_delete_kb(groups),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_delete:"))
async def cb_group_delete(callback: CallbackQuery):
    group_id = int(callback.data.split(":")[1])

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        await remove_user_from_group(db, user.id, group_id)
        groups = await get_user_groups(db, user.id)

    logger.info("user=%d unlinked from group id=%d", callback.from_user.id, group_id)
    await callback.answer("✅ Группа удалена")

    if groups:
        lines = ["📂 <b>Мои группы</b>\n"]
        for i, g in enumerate(groups, 1):
            emoji = STATUS_EMOJI.get(g.status.value, "")
            lines.append(f"{i}. {g.title or g.link} {emoji}")
        text = "\n".join(lines)
    else:
        text = "📂 <b>Мои группы</b>\n\nСписок пуст."

    await callback.message.edit_text(
        text,
        reply_markup=get_groups_list_kb(groups),
        parse_mode="HTML",
    )
