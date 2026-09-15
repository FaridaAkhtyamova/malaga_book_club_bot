from aiogram.fsm.state import State, StatesGroup


class BookSearchStates(StatesGroup):
    waiting_query = State()
    waiting_manual_title = State()
    waiting_manual_authors = State()
    waiting_manual_pages = State()
    waiting_manual_description = State()
    waiting_confirm = State()
