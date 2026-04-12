"""Handler for group link click tracking."""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from shared.database import get_connection, get_or_create_user, get_group_by_id, create_link_click

router = Router()
logger = logging.getLogger(__name__)


def _group_url(group_link: str) -> str:
    if group_link.startswith("@"):
        return f"https://t.me/{group_link[1:]}"
    return group_link


@router.callback_query(F.data.startswith("go:"))
async def cb_go_group(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    match_id = int(parts[1])
    group_id = int(parts[2])

    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        group = await get_group_by_id(db, group_id)
        await create_link_click(db, match_id, group_id, user.id)

    logger.info(
        "user=%d clicked group link: group_id=%d match_id=%d",
        callback.from_user.id, group_id, match_id,
    )

    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return

    url = _group_url(group.link)
    logger.info("Answering callback with url=%s", url)
    await callback.answer(url=url)
