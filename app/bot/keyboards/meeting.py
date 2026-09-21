from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def meeting_invite_keyboard(ics_url: str | None) -> InlineKeyboardMarkup | None:
    if ics_url is None:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Добавить в календарь", url=ics_url)
    return builder.as_markup()
