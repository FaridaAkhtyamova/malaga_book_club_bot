from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.meeting import MeetingInviteChoiceCallback, MeetingPollBookCallback


def meeting_invite_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="По выбранной теме",
        callback_data=MeetingInviteChoiceCallback(action="selected"),
    )
    builder.button(
        text="Другая встреча",
        callback_data=MeetingInviteChoiceCallback(action="other"),
    )
    builder.adjust(1)
    return builder.as_markup()


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
