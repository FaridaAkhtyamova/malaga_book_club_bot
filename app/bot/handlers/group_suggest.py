from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import resolve_suggest_access
from app.repositories.user_repo import UserRepository
from app.services.cycle_service import CycleNotOpenError, CycleService
from app.services.hashtag_suggest import GROUP_HINT, HASHTAG, parse_hashtag_suggestion
from app.services.manual_book import ManualBookService

router = Router()


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.regexp(r"(?i)#выбор_книги"),
)
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

    parsed = parse_hashtag_suggestion(message.text or "")
    if parsed is None:
        await message.reply(
            "Нужны название и число страниц, например:\n"
            f"{HASHTAG} Имя Розы, 500\n"
            "Краткое описание книги"
        )
        return

    user_repo = UserRepository(session)
    user = await user_repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    try:
        _, created = await ManualBookService(session).add(
            user,
            title=parsed.title,
            authors=None,
            description=parsed.description,
            page_count=parsed.page_count,
        )
    except CycleNotOpenError:
        await message.reply("Предложения ещё не открыты.")
        return

    if not created:
        await message.reply("Эта книга уже в списке на голосование.")
        return

    await message.reply("Книга добавлена в список на голосование.")


@router.message(Command("suggest"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_suggest_in_group(message: Message) -> None:
    await message.answer(GROUP_HINT)
