from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin_filter import AdminFilter
from app.services.cycle_service import CycleService, InvalidDayError

router = Router()
router.message.filter(AdminFilter())


@router.message(Command("set_suggest_day"))
async def cmd_set_suggest_day(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
) -> None:
    day = _parse_day(command.args)
    if day is None:
        await message.answer("Укажите день месяца от 1 до 28: /set_suggest_day 15")
        return

    service = CycleService(session)
    try:
        settings = await service.set_suggest_day(day)
    except InvalidDayError as exc:
        await message.answer(str(exc))
        return

    await message.answer(f"День открытия предложений: {settings.suggest_day}.")


@router.message(Command("set_vote_day"))
async def cmd_set_vote_day(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
) -> None:
    day = _parse_day(command.args)
    if day is None:
        await message.answer("Укажите день месяца от 1 до 28: /set_vote_day 25")
        return

    service = CycleService(session)
    try:
        settings = await service.set_vote_day(day)
    except InvalidDayError as exc:
        await message.answer(str(exc))
        return

    await message.answer(f"День запуска опросов: {settings.vote_day}.")


def _parse_day(args: str | None) -> int | None:
    if args is None:
        return None
    raw = args.strip()
    if not raw.isdigit():
        return None
    return int(raw)
