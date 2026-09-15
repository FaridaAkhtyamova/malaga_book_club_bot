from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def calendar_keyboard(google_url: str, apple_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Google Calendar", url=google_url)
    builder.button(text="Календарь iPhone", url=apple_url)
    builder.adjust(1)
    return builder.as_markup()
