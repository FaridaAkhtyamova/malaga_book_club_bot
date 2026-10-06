from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.vote_source_review import VoteSourceReviewCallback


def vote_source_review_keyboard(cycle_id: int, book_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Оставить в голосовании",
        callback_data=VoteSourceReviewCallback(
            action="keep",
            cycle_id=cycle_id,
            book_id=book_id,
        ),
    )
    builder.button(
        text="Убрать",
        callback_data=VoteSourceReviewCallback(
            action="remove",
            cycle_id=cycle_id,
            book_id=book_id,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()
