from aiogram.filters.callback_data import CallbackData


class VoteSourceReviewCallback(CallbackData, prefix="vsource"):
    action: str
    cycle_id: int
    book_id: int
