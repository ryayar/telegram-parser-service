"""Keyboards for patterns section."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from shared.models import Pattern, PatternType


def get_patterns_list_kb(has_patterns: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="pattern_add"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data="pattern_delete_select") if has_patterns
            else InlineKeyboardButton(text="🗑 Удалить", callback_data="pattern_delete_noop"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pattern_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📝 Обычное слово",
            callback_data="pattern_type:exact",
        )],
        [InlineKeyboardButton(
            text="🧠 Умный паттерн",
            callback_data="pattern_type:smart",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="patterns")],
    ])


def get_pattern_delete_kb(patterns: list[Pattern]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in patterns:
        suffix = " (умный)" if p.pattern_type == PatternType.SMART else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{p.value}{suffix}",
                callback_data=f"pattern_delete:{p.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="patterns")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pattern_added_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="pattern_add"),
        InlineKeyboardButton(text="🔑 К словам", callback_data="patterns")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def get_pattern_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="patterns")],
    ])
