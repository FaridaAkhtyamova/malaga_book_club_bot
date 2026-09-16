from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputPollOption, Message, PollOption

from app.bot.keyboards.meeting import calendar_keyboard
from app.bot.keyboards.suggest import suggest_dm_keyboard
from app.db.models import Book, MeetingPoll, SuggestionCycle, VotePoll
from app.services.club_destination import ClubDestination
from app.services.cycle_service import (
    PublishedMeetingPoll,
    PublishedVotePoll,
    format_poll_option,
    poll_question,
)
from app.services.meeting_invite import MeetingInvite
from app.services.meeting_poll import (
    MeetingDateOption,
    meeting_date_runoff_intro,
    meeting_date_runoff_question,
    meeting_poll_intro,
    meeting_poll_question,
    option_date_isos,
    option_labels,
)
from app.services.vote_close import add_poll_votes, runoff_intro_text, runoff_question

_POLL_INTRO = (
    "Голосуем за книгу месяца. Можно выбрать несколько вариантов. "
    "Опросы неанонимные. Когда время вышло, админ закрывает голосование."
)


async def publish_club_announcement(bot: Bot, dest: ClubDestination, text: str) -> None:
    markup = await suggest_dm_keyboard(bot)
    try:
        await bot.send_message(
            dest.chat_id,
            text,
            reply_markup=markup,
            message_thread_id=dest.message_thread_id,
        )
    except TelegramBadRequest:
        if dest.message_thread_id is None:
            raise
        await bot.send_message(dest.chat_id, text, reply_markup=markup)


async def publish_vote_polls(
    bot: Bot,
    dest: ClubDestination,
    cycle: SuggestionCycle,
    chunks: list[list[Book]],
    *,
    runoff: bool = False,
) -> list[PublishedVotePoll]:
    intro = runoff_intro_text() if runoff else _POLL_INTRO
    await bot.send_message(
        dest.chat_id,
        intro,
        message_thread_id=dest.message_thread_id,
    )
    total = len(chunks)
    published: list[PublishedVotePoll] = []
    for index, chunk in enumerate(chunks, start=1):
        used: set[str] = set()
        options: list[InputPollOption | str] = [format_poll_option(book, used) for book in chunk]
        if runoff:
            question = runoff_question(cycle.target_month)
        else:
            question = poll_question(cycle.target_month, index, total)
        message = await bot.send_poll(
            chat_id=dest.chat_id,
            question=question,
            options=options,
            is_anonymous=False,
            allows_multiple_answers=not runoff,
            allow_adding_options=False,
            message_thread_id=dest.message_thread_id,
        )
        recorded = _published_from_message(message, dest.chat_id, chunk)
        if recorded is not None:
            published.append(recorded)
    return published


def _published_from_message(
    message: Message,
    chat_id: int,
    chunk: list[Book],
) -> PublishedVotePoll | None:
    poll = message.poll
    if poll is None:
        return None
    return PublishedVotePoll(
        chat_id=chat_id,
        message_id=message.message_id,
        telegram_poll_id=poll.id,
        book_ids=[book.id for book in chunk],
    )


async def stop_vote_polls(bot: Bot, polls: list[VotePoll]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for poll in polls:
        stopped = await bot.stop_poll(chat_id=poll.chat_id, message_id=poll.message_id)
        add_poll_votes(counts, poll.option_book_ids, stopped.options)
    return counts


async def publish_winner_announcement(
    bot: Bot,
    dest: ClubDestination,
    text: str,
) -> None:
    await bot.send_message(
        dest.chat_id,
        text,
        message_thread_id=dest.message_thread_id,
    )


async def publish_meeting_invite(bot: Bot, dest: ClubDestination, invite: MeetingInvite) -> None:
    document = BufferedInputFile(invite.ics_bytes, filename=invite.filename)
    await bot.send_document(
        chat_id=dest.chat_id,
        document=document,
        caption=invite.caption,
        reply_markup=calendar_keyboard(invite.google_url, invite.apple_url),
        message_thread_id=dest.message_thread_id,
    )


async def publish_meeting_poll(
    bot: Bot,
    dest: ClubDestination,
    title: str,
    choices: list[MeetingDateOption],
    *,
    runoff: bool = False,
    send_intro: bool = True,
) -> PublishedMeetingPoll | None:
    if send_intro:
        intro = meeting_date_runoff_intro() if runoff else meeting_poll_intro(title)
        await bot.send_message(
            dest.chat_id,
            intro,
            message_thread_id=dest.message_thread_id,
        )
    labels = option_labels(choices)
    poll_options: list[InputPollOption | str] = list(labels)
    message = await bot.send_poll(
        chat_id=dest.chat_id,
        question=meeting_date_runoff_question() if runoff else meeting_poll_question(title),
        options=poll_options,
        is_anonymous=False,
        allows_multiple_answers=not runoff,
        allow_adding_options=not runoff,
        message_thread_id=dest.message_thread_id,
    )
    poll = message.poll
    if poll is None:
        return None
    return PublishedMeetingPoll(
        chat_id=dest.chat_id,
        message_id=message.message_id,
        telegram_poll_id=poll.id,
        option_dates=option_date_isos(choices),
    )


async def stop_meeting_polls(
    bot: Bot,
    polls: list[MeetingPoll],
) -> list[tuple[MeetingPoll, list[PollOption]]]:
    stopped: list[tuple[MeetingPoll, list[PollOption]]] = []
    for poll in polls:
        result = await bot.stop_poll(chat_id=poll.chat_id, message_id=poll.message_id)
        stopped.append((poll, list(result.options)))
    return stopped
