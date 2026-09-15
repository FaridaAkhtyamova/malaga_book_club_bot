from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.book import (
    BookConfirmCallback,
    BookMissingCallback,
    BookNavCallback,
    BookSelectCallback,
)
from app.schemas.book import BookSchema

_BUTTON_TEXT_LIMIT = 64
CANCEL_BUTTON = "Отмена"
RETRY_BUTTON = "Искать заново"


def suggest_control_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=RETRY_BUTTON)], [KeyboardButton(text=CANCEL_BUTTON)]],
        resize_keyboard=True,
    )


def search_results_keyboard(books: list[BookSchema]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for book in books:
        author = book.authors[0] if book.authors else "автор не указан"
        label = f"{book.title} — {author}"
        if len(label) > _BUTTON_TEXT_LIMIT:
            label = f"{label[: _BUTTON_TEXT_LIMIT - 1]}…"
        builder.button(
            text=label,
            callback_data=BookSelectCallback(google_id=book.google_id),
        )
    builder.button(
        text="Моей книги нет — добавить самой",
        callback_data=BookMissingCallback(),
    )
    builder.button(text=RETRY_BUTTON, callback_data=BookNavCallback(action="retry"))
    builder.button(text=CANCEL_BUTTON, callback_data=BookNavCallback(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def confirm_send_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить в группу", callback_data=BookConfirmCallback(action="ok"))
    builder.button(text=RETRY_BUTTON, callback_data=BookConfirmCallback(action="retry"))
    builder.button(text=CANCEL_BUTTON, callback_data=BookConfirmCallback(action="no"))
    builder.adjust(1)
    return builder.as_markup()
