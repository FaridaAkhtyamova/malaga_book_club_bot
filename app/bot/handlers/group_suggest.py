from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import resolve_suggest_access
from app.bot.media import cover_file_id
from app.repositories.user_repo import UserRepository
from app.services.cycle_service import CycleNotOpenError, CycleService
from app.services.hashtag_suggest import GROUP_HINT, parse_hashtag_suggestion
from app.services.pending_group_card import PendingGroupCardService

router = Router()

_HASHTAG_FILTER = F.text.regexp(r"(?i)#выбор_книги") | F.caption.regexp(r"(?i)#выбор_книги")
_QUEUED = "Карточка уйдёт админу перед голосованием."


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), _HASHTAG_FILTER)
@router.edited_message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), _HASHTAG_FILTER)
async def on_hashtag_suggestion(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    access = await resolve_suggest_access(
        bot,
        CycleService(session),
        chat_type=message.chat.type,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        thread_id=message.message_thread_id,
    )
    if not access.allowed:
        if access.error:
            await message.reply(access.error)
        return

    raw_text = message.text or message.caption or ""
    parsed = parse_hashtag_suggestion(raw_text)
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    try:
        _, created = await PendingGroupCardService(session).upsert_from_post(
            user,
            chat_id=message.chat.id,
            message_id=message.message_id,
            raw_text=raw_text,
            parsed=parsed,
            cover_url=cover_file_id(message),
        )
    except CycleNotOpenError:
        await message.reply("Предложения ещё не открыты.")
        return

    if created:
        await message.reply(_QUEUED)


@router.message(Command("suggest"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_suggest_in_group(message: Message) -> None:
    await message.answer(GROUP_HINT)
