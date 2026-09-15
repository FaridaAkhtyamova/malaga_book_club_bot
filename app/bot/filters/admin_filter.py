from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.core.config import get_settings


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        return user.id in get_settings().admin_ids
