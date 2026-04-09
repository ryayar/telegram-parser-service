"""Keyboards for groups section."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from shared.models import Group, GroupStatus


STATUS_EMOJI = {
    GroupStatus.ACTIVE: "✅",
    GroupStatus.PENDING: "⏳",
    GroupStatus.ERROR: "❌",
    GroupStatus.LEFT: "🚫",
}


def get_groups_list_kb(groups: list[Group]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for g in groups:
        emoji = STATUS_EMOJI.get(g.status, "")
        label = f"{g.title or g.link} {emoji}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"group_info:{g.id}")])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить", callback_data="group_add"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data="group_delete_select"),
    ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_group_delete_kb(groups: list[Group]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for g in groups:
        rows.append([
            InlineKeyboardButton(
                text=g.title or g.link,
                callback_data=f"group_delete:{g.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="groups")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_group_added_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="group_add"),
        InlineKeyboardButton(text="📂 К группам", callback_data="groups")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="groups")],
    ])
