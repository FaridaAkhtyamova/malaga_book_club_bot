from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_repo import UserRepository

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession) -> None:
    repo = UserRepository(session)
    user = await repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    await message.answer(f"Привет, {user.full_name}! Добро пожаловать в книжный клуб.")
