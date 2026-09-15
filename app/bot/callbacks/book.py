from aiogram.filters.callback_data import CallbackData


class BookSelectCallback(CallbackData, prefix="book"):
    google_id: str


class BookMissingCallback(CallbackData, prefix="nbook"):
    ok: int = 1


class BookConfirmCallback(CallbackData, prefix="bconf"):
    action: str


class BookNavCallback(CallbackData, prefix="bnav"):
    action: str
