from aiogram.types import Message


def cover_file_id(message: object) -> str | None:
    if not isinstance(message, Message):
        return None
    if message.photo:
        return message.photo[-1].file_id
    document = message.document
    if document is None:
        return None
    mime = (document.mime_type or "").lower()
    if mime.startswith("image/"):
        return document.file_id
    return None
