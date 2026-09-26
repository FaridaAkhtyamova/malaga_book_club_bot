from aiogram.filters.callback_data import CallbackData


class MeetingPollBookCallback(CallbackData, prefix="mpoll"):
    action: str
