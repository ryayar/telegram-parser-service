"""Main menu keyboard."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_kb(is_active: bool = True) -> InlineKeyboardMarkup:
    pause_btn = (
        InlineKeyboardButton(text="⏸ Приостановить", callback_data="toggle_pause")
        if is_active
        else InlineKeyboardButton(text="▶️ Возобновить", callback_data="toggle_pause")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📂 Группы", callback_data="groups"),
            InlineKeyboardButton(text="🔑 Слова", callback_data="patterns"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        ],
        [
            InlineKeyboardButton(text="📋 История", callback_data="history"),
        ],
        [pause_btn],
    ])
