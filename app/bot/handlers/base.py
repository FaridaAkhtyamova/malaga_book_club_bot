from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.books import begin_suggest
from app.bot.keyboards.suggest import SUGGEST_START_PAYLOAD
from app.repositories.user_repo import UserRepository

router = Router()


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
        "В группе — отправьте сообщение:\n"
        "#выбор_книги Название книги, 500\n"
        "Краткое описание книги\n"
        "где 500 — количество страниц.\n\n"
        "Здесь, в личке — используйте /suggest. Я помогу найти книгу в каталоге "
        "или добавить её вручную.\n\n"
        "Все предложенные книги попадут в общее голосование."
    )
