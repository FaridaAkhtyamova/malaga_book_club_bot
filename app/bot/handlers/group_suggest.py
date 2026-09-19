from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import BaseFilter
from aiogram.types import Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import resolve_suggest_access
from app.bot.media import cover_file_id
from app.repositories.settings_repo import SettingsRepository
from app.repositories.user_repo import UserRepository
from app.services.cycle_service import CycleNotOpenError
from app.services.hashtag_suggest import parse_hashtag_suggestion, suggest_source_text
from app.services.pending_group_card import PendingGroupCardService

logger = logging.getLogger(__name__)
router = Router()

# Group Anonymous Bot / Channel comment bot — not our book bot.
_ALLOWED_TELEGRAM_BOTS = frozenset({1087968824, 136817688})


class ClubHashtagFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return suggest_source_text(message.text, message.caption) is not None


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), ClubHashtagFilter())
@router.edited_message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), ClubHashtagFilter())
async def on_hashtag_suggestion(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    sender = _club_sender(message)
    if sender is None:
        logger.info(
            "Skip group hashtag: no user or foreign bot chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
        return

    club = await SettingsRepository(session).get_by_chat_id(message.chat.id)
    access = await resolve_suggest_access(
        bot,
        session,
        club,
        chat_type=message.chat.type,
        chat_id=message.chat.id,
        user_id=sender.id,
        thread_id=message.message_thread_id,
    )
    if not access.allowed:
        logger.info(
            "Skip group hashtag: access denied chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
        return

    raw_text = suggest_source_text(message.text, message.caption) or ""
    parsed = parse_hashtag_suggestion(raw_text)
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create_user(
        telegram_id=sender.id,
        username=sender.username,
        full_name=sender.full_name,
    )
    try:
        if club is None:
            return
        _, created = await PendingGroupCardService(session).upsert_from_post(
            user,
            club_id=club.id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            raw_text=raw_text,
            parsed=parsed,
            cover_url=cover_file_id(message),
        )
    except CycleNotOpenError:
        logger.info(
            "Skip group hashtag: cycle not open chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )
        return

    if created:
        logger.info(
            "Queued group card chat_id=%s message_id=%s",
            message.chat.id,
            message.message_id,
        )


def _club_sender(message: Message) -> User | None:
    user = message.from_user
    if user is None:
        return None
    if user.is_bot and user.id not in _ALLOWED_TELEGRAM_BOTS:
        return None
    return user
