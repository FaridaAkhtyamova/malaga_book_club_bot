from datetime import date

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_publish import publish_meeting_invite
from app.bot.filters.admin_filter import AdminFilter
from app.bot.states.meeting import MeetingInviteStates
from app.services.club_destination import DestinationService
from app.services.cycle_service import CycleService, NoMeetingDateError, NoWinnerError
from app.services.meeting_invite import (
    InvalidMeetingTimeError,
    MeetingInPastError,
    build_meeting_invite,
    build_meeting_start,
    parse_meeting_time,
)
from app.services.meeting_poll import format_meeting_day

router = Router()

_MEETING_STATES = StateFilter(MeetingInviteStates)
_ASK_TIME = "Напишите время начала, например 19:00. Встреча продлится 1,5 часа по Малаге."
_CANCELLED = "Создание встречи отменено."


def _ask_time(meeting_day: date, book_title: str) -> str:
    return (
        f"Книга: «{book_title}».\n"
        f"Дата: {format_meeting_day(meeting_day)}.\n"
        f"{_ASK_TIME}"
    )


@router.message(Command("create_meeting"), AdminFilter())
async def cmd_create_meeting(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    dest = await DestinationService(session).get_destination()
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    try:
        book, meeting_day = await CycleService(session).get_selected_meeting()
    except (NoWinnerError, NoMeetingDateError) as exc:
        await message.answer(str(exc))
        return

    await state.update_data(book_title=book.title, meeting_date=meeting_day.isoformat())
    await state.set_state(MeetingInviteStates.waiting_time)
    await message.answer(_ask_time(meeting_day, book.title))


@router.message(Command("cancel"), _MEETING_STATES)
async def cmd_cancel_meeting(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_CANCELLED)


@router.message(MeetingInviteStates.waiting_time, F.text, AdminFilter())
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
    raw_date = data.get("meeting_date")
    book_title = data.get("book_title")
    if not isinstance(raw_date, str) or not isinstance(book_title, str):
        try:
            book, meeting_day = await CycleService(session).get_selected_meeting()
        except (NoWinnerError, NoMeetingDateError) as exc:
            await state.clear()
            await message.answer(str(exc))
            return
        book_title = book.title
        raw_date = meeting_day.isoformat()
        await state.update_data(book_title=book_title, meeting_date=raw_date)

    try:
        hour, minute = parse_meeting_time(message.text)
        start = build_meeting_start(date.fromisoformat(raw_date), hour, minute)
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
