"""Handlers for patterns (keywords) management."""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from shared.database import (
    get_connection,
    get_or_create_user,
    get_user_patterns,
    get_user_groups,
    create_pattern,
    delete_pattern,
    add_pattern_to_all_groups,
)
from shared.models import PatternType
from bot_api.keyboards.patterns import (
    get_patterns_list_kb,
    get_pattern_type_kb,
    get_pattern_delete_kb,
    get_pattern_added_kb,
    get_pattern_cancel_kb,
)
from bot_api.states.user_states import AddPatternState

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "patterns")
async def cb_patterns_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        patterns = await get_user_patterns(db, user.id)

    if patterns:
        lines = ["🔑 <b>Мои ключевые слова</b>\n"]
        for i, p in enumerate(patterns, 1):
            suffix = " <i>(умный)</i>" if p.pattern_type == PatternType.SMART else ""
            lines.append(f"{i}. {p.value}{suffix}")
        text = "\n".join(lines)
    else:
        text = "🔑 <b>Мои ключевые слова</b>\n\nСписок пуст. Добавьте первое слово!"

    await callback.message.edit_text(
        text,
        reply_markup=get_patterns_list_kb(bool(patterns)),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "pattern_add")
async def cb_pattern_add(callback: CallbackQuery, state: FSMContext):
    logger.info("user=%d opened add-pattern dialog", callback.from_user.id)
    await state.set_state(AddPatternState.waiting_for_type)
    await callback.message.edit_text(
        "Выберите тип:\n\n"
        "📝 <b>Обычное слово</b> — точное совпадение\n"
        "🧠 <b>Умный паттерн</b> — учитывает опечатки, замены букв",
        reply_markup=get_pattern_type_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pattern_type:"), AddPatternState.waiting_for_type)
async def cb_pattern_type_selected(callback: CallbackQuery, state: FSMContext):
    pattern_type = callback.data.split(":")[1]
    logger.info("user=%d selected pattern type: %s", callback.from_user.id, pattern_type)
    await state.update_data(pattern_type=pattern_type)
    await state.set_state(AddPatternState.waiting_for_value)

    if pattern_type == "smart":
        hint = (
            "Отправьте слово или фразу:\n\n"
            "Бот создаст паттерн, который найдёт текст даже с:\n"
            "• заменой букв (iPhone → 1Ph0ne)\n"
            "• пробелами (i phone, i-phone)\n"
            "• кириллицей (iрhоne)"
        )
    else:
        hint = "Отправьте слово или фразу для поиска:"

    await callback.message.edit_text(
        hint,
        reply_markup=get_pattern_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AddPatternState.waiting_for_value)
async def msg_pattern_value(message: Message, state: FSMContext):
    value = message.text.strip() if message.text else ""
    logger.info("user=%d sent pattern value: %r", message.from_user.id, value)

    if not value or len(value) > 200:
        logger.warning("user=%d invalid pattern value (empty or >200 chars)", message.from_user.id)
        await message.answer(
            "❌ Слово не должно быть пустым или длиннее 200 символов.",
            reply_markup=get_pattern_cancel_kb(),
        )
        return

    data = await state.get_data()
    pattern_type_str = data.get("pattern_type", "exact")
    pattern_type = PatternType.SMART if pattern_type_str == "smart" else PatternType.EXACT
    await state.clear()

    async with get_connection() as db:
        user = await get_or_create_user(db, message.from_user.id)
        pattern = await create_pattern(db, user.id, value, pattern_type)
        if user.new_pattern_groups:
            await add_pattern_to_all_groups(db, user.id, pattern.id)
            logger.info("user=%d created pattern id=%d type=%s value=%r, added to all groups", message.from_user.id, pattern.id, pattern_type.value, value)
        else:
            logger.info("user=%d created pattern id=%d type=%s value=%r, not added to groups (new_pattern_groups=off)", message.from_user.id, pattern.id, pattern_type.value, value)

    type_label = "🧠 Умный паттерн" if pattern_type == PatternType.SMART else "📝 Обычное слово"
    await message.answer(
        f"✅ <b>{type_label} создан!</b>\n\n"
        f"Значение: <code>{value}</code>",
        reply_markup=get_pattern_added_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "pattern_delete_noop")
async def cb_pattern_delete_noop(callback: CallbackQuery):
    await callback.answer("Нет слов для удаления")


@router.callback_query(F.data == "pattern_delete_select")
async def cb_pattern_delete_select(callback: CallbackQuery):
    async with get_connection() as db:
        user = await get_or_create_user(db, callback.from_user.id)
        patterns = await get_user_patterns(db, user.id)

    if not patterns:
        await callback.answer("Нет слов для удаления")
        return

    await callback.message.edit_text(
        "Выберите слово для удаления:",
        reply_markup=get_pattern_delete_kb(patterns),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pattern_delete:"))
async def cb_pattern_delete(callback: CallbackQuery):
    pattern_id = int(callback.data.split(":")[1])

    async with get_connection() as db:
        await delete_pattern(db, pattern_id)
        user = await get_or_create_user(db, callback.from_user.id)
        patterns = await get_user_patterns(db, user.id)

    logger.info("user=%d deleted pattern id=%d", callback.from_user.id, pattern_id)
    await callback.answer("✅ Слово удалено")

    if patterns:
        lines = ["🔑 <b>Мои ключевые слова</b>\n"]
        for i, p in enumerate(patterns, 1):
            suffix = " <i>(умный)</i>" if p.pattern_type == PatternType.SMART else ""
            lines.append(f"{i}. {p.value}{suffix}")
        text = "\n".join(lines)
    else:
        text = "🔑 <b>Мои ключевые слова</b>\n\nСписок пуст."

    await callback.message.edit_text(
        text,
        reply_markup=get_patterns_list_kb(bool(patterns)),
        parse_mode="HTML",
    )
