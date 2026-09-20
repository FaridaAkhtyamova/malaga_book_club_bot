from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def meeting_invite_keyboard(google_url: str, outlook_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="В календарь", url=google_url)
    builder.button(text="Outlook", url=outlook_url)
    builder.adjust(1)
    return builder.as_markup()
