from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.pending_card import PendingCardCallback


def pending_card_keyboard(card_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="В голосование",
        callback_data=PendingCardCallback(action="ok", card_id=card_id),
    )
    builder.button(
        text="Исправить",
        callback_data=PendingCardCallback(action="edit", card_id=card_id),
    )
    builder.button(
        text="Пропустить",
        callback_data=PendingCardCallback(action="skip", card_id=card_id),
    )
    builder.adjust(1)
    return builder.as_markup()
