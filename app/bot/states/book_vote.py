from aiogram.fsm.state import State, StatesGroup


class WinnerCoverStates(StatesGroup):
    waiting_photo = State()
