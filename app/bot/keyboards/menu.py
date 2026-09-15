from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

SEARCH_BOOK_BUTTON = "Найти книгу"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SEARCH_BOOK_BUTTON)]],
        resize_keyboard=True,
    )
