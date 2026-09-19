from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Chat, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import is_club_admin


class AdminFilter(BaseFilter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        bot: Bot,
        session: AsyncSession,
    ) -> bool:
        user = event.from_user
        if user is None or user.is_bot:
            return False

        chat = _event_chat(event)
        return await is_club_admin(
            bot,
            session,
            user.id,
            current_chat_id=None if chat is None else chat.id,
            current_chat_type=None if chat is None else chat.type,
        )


def _event_chat(event: Message | CallbackQuery) -> Chat | None:
    if isinstance(event, Message):
        return event.chat
    message = event.message
    if message is None:
        return None
    return message.chat
