from aiogram.filters.callback_data import CallbackData


class ClubPickCallback(CallbackData, prefix="club"):
    club_id: int
    action: str
