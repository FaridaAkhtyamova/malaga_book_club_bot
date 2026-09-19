from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.club import ClubPickCallback
from app.db.models import ClubSettings
from app.services.club_destination import club_label


def club_pick_keyboard(
    clubs: Sequence[ClubSettings],
    *,
    action: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for club in clubs:
        builder.button(
            text=club_label(club, limit=64),
            callback_data=ClubPickCallback(club_id=club.id, action=action),
        )
    builder.adjust(1)
    return builder.as_markup()
