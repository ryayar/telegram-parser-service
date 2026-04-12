"""Keyboards for settings section."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


TIMEZONE_OPTIONS = [
    ("UTC+2", "Калининград", 2),
    ("UTC+3", "Москва", 3),
    ("UTC+4", "Самара", 4),
    ("UTC+5", "Екатеринбург", 5),
    ("UTC+6", "Омск", 6),
    ("UTC+7", "Красноярск", 7),
    ("UTC+8", "Иркутск", 8),
    ("UTC+9", "Якутск", 9),
    ("UTC+10", "Владивосток", 10),
    ("UTC+11", "Среднеколымск", 11),
    ("UTC+12", "Камчатка", 12),
]


def get_settings_kb(
    new_group_patterns: bool = False,
    new_pattern_groups: bool = False,
    group_duplicates: bool = True,
) -> InlineKeyboardMarkup:
    ngp = "✅ Вкл" if new_group_patterns else "☐ Выкл"
    npg = "✅ Вкл" if new_pattern_groups else "☐ Выкл"
    gd = "✅ Вкл" if group_duplicates else "☐ Выкл"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Изменить часовой пояс", callback_data="settings_timezone")],
        [InlineKeyboardButton(text="🔕 Изменить тихие часы", callback_data="settings_quiet_hours")],
        [InlineKeyboardButton(
            text=f"📂 Новая группа — все слова: {ngp}",
            callback_data="toggle_new_group_patterns",
        )],
        [InlineKeyboardButton(
            text=f"🔑 Новое слово — все группы: {npg}",
            callback_data="toggle_new_pattern_groups",
        )],
        [InlineKeyboardButton(
            text=f"🗂 Группировать дубли: {gd}",
            callback_data="toggle_group_duplicates",
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])


def get_timezone_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for utc_label, city, offset in TIMEZONE_OPTIONS:
        row.append(InlineKeyboardButton(
            text=f"{utc_label} {city}",
            callback_data=f"tz:{offset}",
        ))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_quiet_hours_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Отключить тихие часы", callback_data="quiet_hours_off")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")],
    ])
