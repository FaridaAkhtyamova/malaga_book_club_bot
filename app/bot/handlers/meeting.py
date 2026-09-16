from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_publish import publish_meeting_invite
from app.bot.filters.admin_filter import AdminFilter
from app.bot.states.meeting import MeetingInviteStates
from app.core.config import get_settings
from app.services.club_destination import DestinationService
from app.services.cycle_service import CycleService
from app.services.meeting_invite import (
    InvalidMeetingDateError,
    InvalidMeetingTimeError,
    MeetingInPastError,
    build_meeting_invite,
    build_meeting_start,
    parse_meeting_date,
    parse_meeting_time,
)
from app.services.meeting_poll import format_meeting_day

router = Router()
router.message.filter(AdminFilter())

_MEETING_STATES = StateFilter(MeetingInviteStates)
_ASK_DATE = "Дата встречи ещё не выбрана. Напишите её как 25.09 или 25.09.2026."
_ASK_TIME = "Напишите время начала, например 19:00. Встреча продлится 1,5 часа по Малаге."
_ASK_TITLE = "Книга ещё не выбрана. Напишите название для приглашения."
_CANCELLED = "Создание встречи отменено."
_DATE_PAST = "Эта дата уже прошла. Напишите другую."


def _ask_time(meeting_day: date, book_title: str) -> str:
    return (
        f"Книга: «{book_title}».\n"
        f"Дата: {format_meeting_day(meeting_day)}.\n"
        f"{_ASK_TIME}"
    )


def _ask_title(meeting_day: date) -> str:
    return f"Дата: {format_meeting_day(meeting_day)}.\n{_ASK_TITLE}"


def _stored_title(data: dict[str, object]) -> str | None:
    stored = data.get("book_title")
    if isinstance(stored, str):
        title = stored.strip()
        return title or None
    return None


def _stored_day(data: dict[str, object]) -> date | None:
    raw_date = data.get("meeting_date")
    if isinstance(raw_date, str):
        return date.fromisoformat(raw_date)
    return None


def _is_past_day(meeting_day: date) -> bool:
    today = datetime.now(ZoneInfo(get_settings().TIMEZONE)).date()
    return meeting_day < today


async def _prompt_meeting_step(
    message: Message,
    state: FSMContext,
    *,
    meeting_day: date | None,
    book_title: str | None,
) -> None:
    if book_title is not None:
        await state.update_data(book_title=book_title)
    if meeting_day is None:
        await state.set_state(MeetingInviteStates.waiting_date)
        await message.answer(_ASK_DATE)
        return
    await state.update_data(meeting_date=meeting_day.isoformat())
    if book_title is None:
        await state.set_state(MeetingInviteStates.waiting_title)
        await message.answer(_ask_title(meeting_day))
        return
    await state.set_state(MeetingInviteStates.waiting_time)
    await message.answer(_ask_time(meeting_day, book_title))


@router.message(Command("create_meeting"))
async def cmd_create_meeting(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    dest = await DestinationService(session).get_destination()
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    book_title, meeting_day = await CycleService(session).get_selected_meeting()
    await _prompt_meeting_step(message, state, meeting_day=meeting_day, book_title=book_title)


@router.message(Command("cancel"), _MEETING_STATES)
async def cmd_cancel_meeting(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_CANCELLED)


@router.message(MeetingInviteStates.waiting_date, F.text)
async def on_meeting_date(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.text is None:
        return

    try:
        meeting_day = parse_meeting_date(message.text)
    except InvalidMeetingDateError as exc:
        await message.answer(str(exc))
        return
    if _is_past_day(meeting_day):
        await message.answer(_DATE_PAST)
        return

    service = CycleService(session)
    cycle = await service.get_latest_cycle()
    if cycle is not None:
        await service.apply_meeting_date(cycle, meeting_day)

    data = await state.get_data()
    book_title = _stored_title(data)
    if book_title is None:
        book_title, _ = await service.get_selected_meeting()
    await _prompt_meeting_step(message, state, meeting_day=meeting_day, book_title=book_title)


@router.message(MeetingInviteStates.waiting_title, F.text)
async def on_meeting_title(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(_ASK_TITLE)
        return

    data = await state.get_data()
    meeting_day = _stored_day(data)
    if meeting_day is None:
        _, meeting_day = await CycleService(session).get_selected_meeting()
    await _prompt_meeting_step(message, state, meeting_day=meeting_day, book_title=title)


@router.message(MeetingInviteStates.waiting_time, F.text)
async def on_meeting_time(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if message.text is None:
        return

    dest = await DestinationService(session).get_destination()
    if dest is None:
        await state.clear()
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    data = await state.get_data()
    meeting_day = _stored_day(data)
    book_title = _stored_title(data)
    if meeting_day is None or book_title is None:
        cycle_title, cycle_day = await CycleService(session).get_selected_meeting()
        meeting_day = meeting_day or cycle_day
        book_title = book_title or cycle_title
        if meeting_day is None or book_title is None:
            await _prompt_meeting_step(
                message, state, meeting_day=meeting_day, book_title=book_title
            )
            return
        await state.update_data(book_title=book_title, meeting_date=meeting_day.isoformat())

    try:
        hour, minute = parse_meeting_time(message.text)
        start = build_meeting_start(meeting_day, hour, minute)
    except InvalidMeetingTimeError as exc:
        await message.answer(str(exc))
        return
    except MeetingInPastError:
        await message.answer("Это время уже прошло. Напишите другое время.")
        return

    invite = build_meeting_invite(start, book_title=book_title)
    await publish_meeting_invite(bot, dest, invite)
    await state.clear()

    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if not same_thread:
        await message.answer("Приглашение в календарь опубликовано в группе.")
