from datetime import datetime

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, PhotoSize

from app.bot.media import cover_file_id


def test_cover_file_id_uses_largest_photo_variant() -> None:
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=1, type=ChatType.PRIVATE),
        photo=[
            PhotoSize(file_id="small-cover", file_unique_id="small", width=100, height=100),
            PhotoSize(file_id="large-cover", file_unique_id="large", width=500, height=500),
        ],
    )

    assert cover_file_id(message) == "large-cover"