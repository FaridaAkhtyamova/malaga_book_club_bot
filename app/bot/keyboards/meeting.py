from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def meeting_invite_keyboard(
    *,
    ics_url: str | None,
    google_url: str,
    outlook_url: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ics_url is not None:
        builder.button(text="📅 Добавить в календарь", url=ics_url)
        builder.button(text="Google Календарь", url=google_url)
        builder.button(text="Outlook", url=outlook_url)
    else:
        builder.button(text="📅 Добавить в календарь", url=google_url)
        builder.button(text="Outlook", url=outlook_url)
    builder.adjust(1)
    return builder.as_markup()
