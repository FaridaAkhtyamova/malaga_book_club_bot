from aiogram.filters.callback_data import CallbackData


class PendingCardCallback(CallbackData, prefix="pcard"):
    action: str
    card_id: int
