from aiogram.filters.callback_data import CallbackData


class MeetingPollBookCallback(CallbackData, prefix="mpoll"):
    action: str


class MeetingInviteChoiceCallback(CallbackData, prefix="minvite"):
    action: str
