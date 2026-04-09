"""FSM states for user interactions."""
from aiogram.fsm.state import State, StatesGroup


class AddGroupState(StatesGroup):
    waiting_for_link = State()


class AddPatternState(StatesGroup):
    waiting_for_type = State()
    waiting_for_value = State()


class SettingsState(StatesGroup):
    waiting_for_timezone = State()
    waiting_for_quiet_hours = State()
