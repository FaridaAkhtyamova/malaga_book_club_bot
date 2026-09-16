from aiogram.fsm.state import State, StatesGroup


class PendingCardStates(StatesGroup):
    waiting_title = State()
    waiting_authors = State()
    waiting_pages = State()
    waiting_description = State()
