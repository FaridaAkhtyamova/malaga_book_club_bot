from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputPollOption, Message

from app.bot.keyboards.meeting import google_calendar_keyboard
from app.bot.keyboards.suggest import suggest_dm_keyboard
from app.db.models import Book, SuggestionCycle, VotePoll
from app.services.club_destination import ClubDestination
from app.services.cycle_service import (
    PublishedVotePoll,
    format_poll_option,
    poll_question,
)
from app.services.meeting_invite import MeetingInvite
from app.services.meeting_poll import meeting_poll_intro, meeting_poll_question
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
        reply_markup=google_calendar_keyboard(invite.google_url),
        message_thread_id=dest.message_thread_id,
    )


async def publish_meeting_poll(
    bot: Bot,
    dest: ClubDestination,
    title: str,
    options: list[str],
) -> None:
    await bot.send_message(
        dest.chat_id,
        meeting_poll_intro(title),
        message_thread_id=dest.message_thread_id,
    )
    poll_options: list[InputPollOption | str] = list(options)
    await bot.send_poll(
        chat_id=dest.chat_id,
        question=meeting_poll_question(title),
        options=poll_options,
        is_anonymous=False,
        allows_multiple_answers=True,
        allow_adding_options=True,
        message_thread_id=dest.message_thread_id,
    )
