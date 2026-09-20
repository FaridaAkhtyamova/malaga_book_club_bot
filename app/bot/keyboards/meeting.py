from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def meeting_invite_keyboard(
    *,
    ics_url: str,
    google_url: str,
    outlook_url: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Добавить в календарь", url=ics_url)
    builder.button(text="Google Календарь", url=google_url)
    builder.button(text="Outlook", url=outlook_url)
    builder.adjust(1)
    return builder.as_markup()
