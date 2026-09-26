from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.meeting import MeetingPollBookCallback


def meeting_poll_book_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="По книге месяца",
        callback_data=MeetingPollBookCallback(action="month"),
    )
    builder.button(
        text="Для другой книги",
        callback_data=MeetingPollBookCallback(action="other"),
    )
    builder.adjust(1)
    return builder.as_markup()
