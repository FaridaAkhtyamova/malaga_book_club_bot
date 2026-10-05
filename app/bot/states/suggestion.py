from aiogram.fsm.state import State, StatesGroup


class RemoveSuggestionStates(StatesGroup):
    waiting_book_id = State()