from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import is_club_admin
from app.bot.commands import admin_command_names, format_help
from app.bot.handlers.books import begin_suggest
from app.bot.keyboards.suggest import SUGGEST_START_PAYLOAD
from app.repositories.user_repo import UserRepository
from app.services.cycle_service import CycleService

router = Router()

_ADMIN_ONLY = "Эта команда доступна только админу клуба."


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    repo = UserRepository(session)
    user = await repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    payload = (command.args or "").strip()
    if payload == SUGGEST_START_PAYLOAD:
        await begin_suggest(message, state, session, bot)
        return

    name = user.full_name or "друг"
    await message.answer(
        f"Привет, {name}! 👋\n"
        "Я помогу собрать книги для следующего голосования книжного клуба 📚\n\n"
        "Когда открыт сбор предложений, добавить книгу можно двумя способами:\n\n"
        "В группе — карточка с #выбор_книги: название, автор, страницы (стр / страниц). "
        "Кто предложил, берётся из сообщения. Перед голосованием карточку проверит админ.\n\n"
        "Здесь, в личке — используйте /suggest. Я помогу найти книгу в каталоге "
        "или добавить её вручную.\n\n"
        "Книги из лички и одобренные карточки из группы попадут в общее голосование.\n\n"
        "Список команд: /help"
    )


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot, session: AsyncSession) -> None:
    user = message.from_user
    is_admin = user is not None and await is_club_admin(
        bot,
        CycleService(session),
        user.id,
        current_chat_id=message.chat.id,
        current_chat_type=message.chat.type,
    )
    await message.answer(format_help(is_admin=is_admin))


@router.message(Command(*admin_command_names()))
async def cmd_admin_only(message: Message) -> None:
    await message.answer(_ADMIN_ONLY)
