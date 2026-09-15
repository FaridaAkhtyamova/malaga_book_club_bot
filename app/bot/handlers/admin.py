from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin_filter import AdminFilter
from app.bot.polls import publish_vote_polls
from app.services.cycle_service import (
    CycleAlreadyOpenError,
    CycleNotOpenError,
    CycleService,
    GroupNotSetError,
    InvalidDayError,
    NotEnoughBooksError,
    month_name_ru,
)

router = Router()


@router.message(Command("set_group"), AdminFilter())
async def cmd_set_group(message: Message, session: AsyncSession) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Эту команду нужно вызвать в группе клуба.")
        return

    service = CycleService(session)
    await service.bind_group(message.chat.id)
    await message.answer("Группа привязана. Анонсы и опросы будут публиковаться здесь.")


@router.message(Command("set_suggest_day"), AdminFilter())
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


@router.message(Command("set_vote_day"), AdminFilter())
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


@router.message(Command("open_suggestions"), AdminFilter())
async def cmd_open_suggestions(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    service = CycleService(session)
    try:
        cycle, text = await service.open_suggestions_for_next_month()
        settings = await service.get_settings()
    except GroupNotSetError as exc:
        await message.answer(str(exc))
        return
    except CycleAlreadyOpenError as exc:
        await message.answer(str(exc))
        return

    if settings.group_chat_id is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    await bot.send_message(settings.group_chat_id, text)
    month = month_name_ru(cycle.target_month)
    if message.chat.id != settings.group_chat_id:
        await message.answer(f"Сбор предложений на {month} открыт, анонс опубликован в группе.")


@router.message(Command("start_vote"), AdminFilter())
async def cmd_start_vote(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    service = CycleService(session)
    settings = await service.get_settings()
    if settings.group_chat_id is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    try:
        cycle, chunks = await service.prepare_vote()
    except CycleNotOpenError as exc:
        await message.answer(str(exc))
        return
    except NotEnoughBooksError as exc:
        await message.answer(str(exc))
        return

    try:
        await publish_vote_polls(bot, settings.group_chat_id, cycle, chunks)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось опубликовать опросы: {exc}")
        return

    await service.mark_voting(cycle)
    if message.chat.id != settings.group_chat_id:
        await message.answer("Опросы опубликованы в группе.")


@router.message(Command("cycle_status"), AdminFilter())
async def cmd_cycle_status(message: Message, session: AsyncSession) -> None:
    service = CycleService(session)
    settings = await service.get_settings()
    cycle = await service.get_latest_cycle()

    group = str(settings.group_chat_id) if settings.group_chat_id is not None else "не задана"
    suggest_day = str(settings.suggest_day) if settings.suggest_day is not None else "не задан"
    vote_day = str(settings.vote_day) if settings.vote_day is not None else "не задан"

    lines = [
        f"Группа: {group}",
        f"День предложений: {suggest_day}",
        f"День голосования: {vote_day}",
        f"Час анонса: {settings.announce_hour}:00",
    ]

    if cycle is None:
        lines.append("Текущий цикл: нет")
    else:
        count = await service.count_suggestions(cycle.id)
        month = month_name_ru(cycle.target_month)
        lines.append(f"Цикл: {month} {cycle.target_year}, статус {cycle.status}, книг: {count}")

    await message.answer("\n".join(lines))


def _parse_day(args: str | None) -> int | None:
    if args is None:
        return None
    raw = args.strip()
    if not raw.isdigit():
        return None
    return int(raw)
