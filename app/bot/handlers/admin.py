from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin_filter import AdminFilter
from app.bot.club_chat import clubs_where_admin
from app.bot.club_context import require_admin_club
from app.bot.states.admin import ScheduleDayStates
from app.db.models import ClubSettings
from app.services.cycle_service import CycleService, InvalidDayError

router = Router()
router.message.filter(AdminFilter(), F.chat.type == ChatType.PRIVATE)


@router.message(Command("set_suggest_day"))
async def cmd_set_suggest_day(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
) -> None:
    day = _parse_day(command.args)
    if day is None:
        if command.args:
            await message.answer(
                "Укажите целое число от 0 до 28: /set_suggest_day 15 "
                "(0 — отключить автоматику)."
            )
            return
        club = await require_admin_club(message, bot, session)
        if club is None:
            return
        await state.update_data(schedule_day_kind="suggest", schedule_day_club_id=club.id)
        await state.set_state(ScheduleDayStates.waiting_day)
        await message.answer("Введите день открытия сбора от 0 до 28 (0 — отключить автоматику).")
        return

    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    await _set_schedule_day(message, session, club, "suggest", day)


@router.message(Command("set_vote_day"))
async def cmd_set_vote_day(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext,
) -> None:
    day = _parse_day(command.args)
    if day is None:
        if command.args:
            await message.answer(
                "Укажите целое число от 0 до 28: /set_vote_day 25 "
                "(0 — отключить автоматику)."
            )
            return
        club = await require_admin_club(message, bot, session)
        if club is None:
            return
        await state.update_data(schedule_day_kind="vote", schedule_day_club_id=club.id)
        await state.set_state(ScheduleDayStates.waiting_day)
        await message.answer(
            "Введите день запуска голосования от 0 до 28 (0 — отключить автоматику)."
        )
        return

    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    await _set_schedule_day(message, session, club, "vote", day)


@router.message(Command("cancel"), ScheduleDayStates.waiting_day)
async def cancel_schedule_day(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Изменение дня автоматического действия отменено.")


@router.message(ScheduleDayStates.waiting_day, F.text, ~F.text.startswith("/"))
async def process_schedule_day(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    day = _parse_day(message.text)
    if day is None:
        await message.answer("Введите целое число от 0 до 28 или /cancel.")
        return

    data = await state.get_data()
    club_id = data.get("schedule_day_club_id")
    kind = data.get("schedule_day_kind")
    if not isinstance(club_id, int) or kind not in {"suggest", "vote"}:
        await state.clear()
        await message.answer("Не удалось определить настройку. Повторите команду.")
        return

    actor_id = None if message.from_user is None else message.from_user.id
    clubs = [] if actor_id is None else await clubs_where_admin(bot, session, actor_id)
    club = next((item for item in clubs if item.id == club_id), None)
    if club is None:
        await state.clear()
        await message.answer("Вы больше не администратор этого клуба.")
        return

    if await _set_schedule_day(message, session, club, kind, day):
        await state.clear()


async def _set_schedule_day(
    message: Message,
    session: AsyncSession,
    club: ClubSettings,
    kind: str,
    day: int,
) -> bool:
    service = CycleService(session, club)
    try:
        if kind == "suggest":
            settings = await service.set_suggest_day(day)
        else:
            settings = await service.set_vote_day(day)
    except InvalidDayError as exc:
        await message.answer(str(exc))
        return False

    if kind == "suggest":
        if settings.suggest_day == 0:
            await message.answer("Автоматическое открытие сбора книг отключено.")
        else:
            await message.answer(f"День открытия предложений: {settings.suggest_day}.")
    elif settings.vote_day == 0:
        await message.answer("Автоматический запуск голосования отключён.")
    else:
        await message.answer(f"День запуска опросов: {settings.vote_day}.")
    return True


def _parse_day(args: str | None) -> int | None:
    if args is None:
        return None
    raw = args.strip()
    if not raw.isdigit():
        return None
    return int(raw)
