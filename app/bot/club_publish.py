from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InputPollOption

from app.bot.keyboards.suggest import suggest_dm_keyboard
from app.db.models import Book, SuggestionCycle
from app.services.club_destination import ClubDestination
from app.services.cycle_service import format_poll_option, poll_question
from app.services.meeting_poll import meeting_poll_intro, meeting_poll_question

_POLL_INTRO = (
    "Голосуем за книгу месяца. Можно выбрать несколько вариантов "
    "и добавить свой, если книги нет в списке. "
    "Опросы неанонимные. Если опросов несколько, можно проголосовать в каждом."
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
) -> None:
    await bot.send_message(
        dest.chat_id,
        _POLL_INTRO,
        message_thread_id=dest.message_thread_id,
    )
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        used: set[str] = set()
        options: list[InputPollOption | str] = [format_poll_option(book, used) for book in chunk]
        await bot.send_poll(
            chat_id=dest.chat_id,
            question=poll_question(cycle.target_month, index, total),
            options=options,
            is_anonymous=False,
            allows_multiple_answers=True,
            allow_adding_options=True,
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
