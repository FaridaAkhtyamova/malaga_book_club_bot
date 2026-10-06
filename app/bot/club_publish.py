from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BufferedInputFile,
    InputPollOption,
    Message,
    PollOption,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import club_admin_user_ids, send_html_card, send_with_topic_fallback
from app.bot.keyboards.pending_card import pending_card_keyboard
from app.bot.keyboards.suggest import suggest_dm_keyboard
from app.bot.keyboards.vote_source_review import vote_source_review_keyboard
from app.bot.media import cover_file_id
from app.db.models import (
    Book,
    MeetingPoll,
    MeetingTimePoll,
    PendingGroupCard,
    SuggestionCycle,
    VotePoll,
)
from app.repositories.suggestion_repo import SuggestionRepository
from app.services.club_destination import ClubDestination
from app.services.cycle_service import (
    CycleService,
    PublishedMeetingPoll,
    PublishedMeetingTimePoll,
    PublishedVotePoll,
    chunk_books_for_polls,
    format_poll_option,
    poll_question,
)
from app.services.meeting_invite import MeetingInvite
from app.services.meeting_poll import (
    MeetingDateOption,
    MeetingTimeOption,
    meeting_date_runoff_intro,
    meeting_date_runoff_question,
    meeting_poll_intro,
    meeting_poll_question,
    meeting_time_poll_intro,
    meeting_time_poll_question,
    meeting_time_runoff_intro,
    meeting_time_runoff_question,
    option_date_isos,
    option_hours,
    option_labels,
)
from app.services.pending_group_card import PendingGroupCardService, format_card_preview
from app.services.vote_close import add_poll_votes, runoff_intro_text, runoff_question

logger = logging.getLogger(__name__)

_POLL_INTRO = (
    "🗳️ Голосуем за книгу месяца. Можно выбрать несколько вариантов. "
    "Опросы неанонимные. Когда время вышло, админ закрывает голосование."
)


@dataclass(frozen=True, slots=True)
class BookSourceReview:
    cycle_id: int
    book: Book
    source_chat_id: int | None
    source_message_id: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class BookSourceCheck:
    chunks: list[list[Book]]
    needs_review: list[BookSourceReview]


async def publish_club_announcement(bot: Bot, dest: ClubDestination, text: str) -> None:
    markup = await suggest_dm_keyboard(bot)
    await send_with_topic_fallback(
        lambda thread_id: bot.send_message(
            dest.chat_id,
            text,
            reply_markup=markup,
            message_thread_id=thread_id,
        ),
        chat_id=dest.chat_id,
        message_thread_id=dest.message_thread_id,
        operation="Club announcement",
    )


async def filter_books_with_available_messages(
    bot: Bot,
    books: Sequence[Book],
    source_messages: Mapping[int, tuple[int, int]],
    *,
    cycle_id: int,
    reviewed_book_ids: set[int] | None = None,
) -> BookSourceCheck:
    available: list[Book] = []
    needs_review: list[BookSourceReview] = []
    checked = 0
    unavailable = 0
    without_source = 0
    reviewed = 0
    for book in books:
        if reviewed_book_ids is not None and book.id in reviewed_book_ids:
            reviewed += 1
            available.append(book)
            logger.info("Book %s approved for voting by an administrator", book.id)
            continue

        source = source_messages.get(book.id)
        if source is None:
            without_source += 1
            logger.info(
                "Book %s has no source Telegram message; marking it for admin review",
                book.id,
            )
            needs_review.append(
                BookSourceReview(
                    cycle_id=cycle_id,
                    book=book,
                    source_chat_id=None,
                    source_message_id=None,
                    reason="source Telegram message is unknown",
                )
            )
            continue

        chat_id, message_id = source
        checked += 1
        try:
            copied = await bot.copy_message(
                chat_id=chat_id,
                from_chat_id=chat_id,
                message_id=message_id,
            )
        except TelegramAPIError as exc:
            logger.info(
                "Source Telegram message %s/%s for book %s is unavailable; "
                "marking it for admin review: %s",
                chat_id,
                message_id,
                book.id,
                exc,
            )
            unavailable += 1
            needs_review.append(
                BookSourceReview(
                    cycle_id=cycle_id,
                    book=book,
                    source_chat_id=chat_id,
                    source_message_id=message_id,
                    reason=str(exc),
                )
            )
            continue

        available.append(book)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=copied.message_id)
        except TelegramAPIError as exc:
            logger.warning(
                "Could not delete temporary copy of book %s message %s/%s: %s",
                book.id,
                chat_id,
                copied.message_id,
                exc,
            )

    chunks = chunk_books_for_polls(available)
    logger.info(
        "Vote source-message check complete: books=%s checked=%s unavailable=%s "
        "without_source=%s admin_approved=%s kept=%s needs_review=%s poll_chunks=%s",
        len(books),
        checked,
        unavailable,
        without_source,
        reviewed,
        len(available),
        len(needs_review),
        len(chunks),
    )
    return BookSourceCheck(chunks=chunks, needs_review=needs_review)


async def check_vote_book_sources(
    bot: Bot,
    service: CycleService,
    cycle: SuggestionCycle,
    books: Sequence[Book],
) -> BookSourceCheck:
    suggestions = await service.suggestion_repo.list_suggestions(cycle.id)
    source_messages: dict[int, tuple[int, int]] = {}
    reviewed_book_ids: set[int] = set()
    for suggestion in suggestions:
        if suggestion.source_reviewed:
            reviewed_book_ids.add(suggestion.book_id)
            continue
        if suggestion.source_chat_id is None or suggestion.source_message_id is None:
            logger.warning(
                "Suggestion has incomplete Telegram source linkage "
                "(cycle_id=%s, suggestion_id=%s, book_id=%s, source_chat_id=%s, "
                "source_message_id=%s)",
                cycle.id,
                suggestion.id,
                suggestion.book_id,
                suggestion.source_chat_id,
                suggestion.source_message_id,
            )
            continue
        source_messages[suggestion.book_id] = (
            suggestion.source_chat_id,
            suggestion.source_message_id,
        )

    logger.info(
        "Starting book source check for cycle %s: books=%s with_source_message=%s",
        cycle.id,
        len(books),
        len(source_messages),
    )
    return await filter_books_with_available_messages(
        bot,
        books,
        source_messages,
        cycle_id=cycle.id,
        reviewed_book_ids=reviewed_book_ids,
    )


def format_vote_source_review(check: BookSourceCheck) -> str:
    lines = [
        "Перед запуском голосования проверьте эти книги. "
        "Подтвердите корректные книги кнопкой «Оставить в голосовании», "
        "ошибочные уберите. Затем повторите /start_vote."
    ]
    for item in check.needs_review:
        lines.append(format_vote_source_review_item(item))
    return "\n".join(lines)


async def notify_vote_source_review(
    bot: Bot,
    chat_id: int,
    cycle_id: int,
    check: BookSourceCheck,
) -> str | None:
    if not check.needs_review:
        return None
    text = format_vote_source_review(check)
    admin_ids = await club_admin_user_ids(bot, chat_id)
    if not admin_ids:
        logger.warning(
            "Could not deliver vote source review for chat %s: no admins found",
            chat_id,
        )
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                admin_id,
                "Проверьте книги перед голосованием. "
                "Подтвердите книгу или уберите её кнопкой ниже.",
            )
        except TelegramAPIError as exc:
            logger.warning(
                "Could not send vote source review intro to admin %s in chat %s: %s",
                admin_id,
                chat_id,
                exc,
            )
            continue
        for item in check.needs_review:
            try:
                await bot.send_message(
                    admin_id,
                    format_vote_source_review_item(item),
                    reply_markup=vote_source_review_keyboard(
                        item.cycle_id,
                        item.book.id,
                    ),
                )
            except TelegramAPIError as exc:
                logger.warning(
                    "Could not send vote source review for book %s to admin %s: %s",
                    item.book.id,
                    admin_id,
                    exc,
                )
    logger.warning(
        "Vote for cycle %s paused for admin review: book_ids=%s",
        cycle_id,
        [item.book.id for item in check.needs_review],
    )
    return text


def format_vote_source_review_item(item: BookSourceReview) -> str:
    book = item.book
    source = (
        f"{item.source_chat_id}/{item.source_message_id}"
        if item.source_chat_id is not None and item.source_message_id is not None
        else "не зарегистрировано"
    )
    pages = f"{book.page_count} стр." if book.page_count is not None else "страниц не указано"
    return (
        f"ID {book.id}: {book.title} — {book.authors or 'автор не указан'}; "
        f"{pages}; сообщение {source} недоступно ({item.reason})."
    )


async def sync_suggestion_buttons(
    bot: Bot,
    session: AsyncSession,
    club_id: int,
    *,
    enabled: bool,
) -> None:
    user_ids = await SuggestionRepository(session).list_user_ids_for_club(club_id)
    text = (
        "Сбор предложений открыт. Отправьте название книги сюда, чтобы найти её в каталоге."
        if enabled
        else "Голосование началось. Сейчас новые книги не принимаются."
    )
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text, reply_markup=ReplyKeyboardRemove())
        except TelegramAPIError as exc:
            logger.info("Could not sync suggestion button for user %s: %s", user_id, exc)


async def publish_vote_polls(
    bot: Bot,
    dest: ClubDestination,
    cycle: SuggestionCycle,
    chunks: list[list[Book]],
    *,
    runoff: bool = False,
) -> list[PublishedVotePoll]:
    intro = runoff_intro_text() if runoff else _POLL_INTRO
    thread_id = dest.message_thread_id
    _, thread_id = await send_with_topic_fallback(
        lambda current_thread_id: bot.send_message(
            dest.chat_id,
            intro,
            message_thread_id=current_thread_id,
        ),
        chat_id=dest.chat_id,
        message_thread_id=thread_id,
        operation="Vote poll intro",
    )

    total = len(chunks)
    published: list[PublishedVotePoll] = []
    try:
        for index, chunk in enumerate(chunks, start=1):
            used: set[str] = set()
            options: list[InputPollOption | str] = [
                format_poll_option(book, used) for book in chunk
            ]
            if runoff:
                question = runoff_question(cycle.target_month)
            else:
                question = poll_question(cycle.target_month, index, total)

            async def send_vote_poll(
                current_thread_id: int | None,
                question: str = question,
                options: list[InputPollOption | str] = options,
            ) -> Message:
                return await bot.send_poll(
                    chat_id=dest.chat_id,
                    question=question,
                    options=options,
                    is_anonymous=False,
                    allows_multiple_answers=not runoff,
                    allow_adding_options=False,
                    message_thread_id=current_thread_id,
                )

            message, thread_id = await send_with_topic_fallback(
                send_vote_poll,
                chat_id=dest.chat_id,
                message_thread_id=thread_id,
                operation=f"Vote poll {index}/{total}",
            )
            recorded = _published_from_message(message, dest.chat_id, chunk)
            if recorded is not None:
                published.append(recorded)
    except Exception:
        await stop_polls_quietly(bot, published)
        raise
    return published


async def stop_polls_quietly(
    bot: Bot,
    polls: Sequence[VotePoll | MeetingPoll | MeetingTimePoll | PublishedVotePoll],
) -> None:
    for poll in polls:
        try:
            await bot.stop_poll(chat_id=poll.chat_id, message_id=poll.message_id)
        except TelegramAPIError as exc:
            logger.warning(
                "Could not stop poll %s/%s: %s",
                poll.chat_id,
                poll.message_id,
                exc,
            )


async def record_vote_polls_or_stop(
    bot: Bot,
    service: CycleService,
    cycle: SuggestionCycle,
    polls: Sequence[PublishedVotePoll],
    *,
    mark_voting: bool = False,
) -> None:
    try:
        await service.record_vote_polls(cycle, polls, mark_voting=mark_voting)
    except Exception:
        await service.session.rollback()
        await stop_polls_quietly(bot, polls)
        raise


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
    cover_url: str | None = None,
) -> None:
    await send_html_card(
        bot,
        dest.chat_id,
        text,
        cover_url,
        dest.message_thread_id,
        parse_mode=None,
    )


async def notify_admins(bot: Bot, text: str, chat_id: int) -> None:
    admin_ids = await club_admin_user_ids(bot, chat_id)
    if not admin_ids:
        logger.warning("No Telegram admins available for notification in chat %s", chat_id)
        return
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError as exc:
            logger.warning(
                "Could not send club admin notification to user %s for chat %s: %s",
                admin_id,
                chat_id,
                exc,
            )
            continue


_PENDING_INTRO = (
    "Перед голосованием проверьте карточки из группы. "
    "Опросы не опубликуются, пока очередь не разберут."
)


async def send_pending_card_reviews(
    bot: Bot,
    cards: list[PendingGroupCard],
    session: AsyncSession,
) -> None:
    if not cards:
        return
    for admin_id in await club_admin_user_ids(bot, cards[0].chat_id):
        try:
            await bot.send_message(admin_id, _PENDING_INTRO)
        except TelegramAPIError:
            continue
        for card in cards:
            await _send_pending_card(bot, admin_id, card, session)


async def _send_pending_card(
    bot: Bot,
    admin_id: int,
    card: PendingGroupCard,
    session: AsyncSession,
) -> None:
    try:
        forwarded = await bot.forward_message(
            chat_id=admin_id,
            from_chat_id=card.chat_id,
            message_id=card.message_id,
        )
        file_id = cover_file_id(forwarded)
        if file_id:
            saved = await PendingGroupCardService(session).set_cover(card.id, file_id)
            if saved is not None:
                card.cover_url = saved.cover_url
    except TelegramAPIError as exc:
        logger.warning(
            "Could not forward group card %s (%s/%s) to admin %s: %s",
            card.id,
            card.chat_id,
            card.message_id,
            admin_id,
            exc,
        )
        try:
            await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=card.chat_id,
                message_id=card.message_id,
            )
        except TelegramAPIError as copy_exc:
            logger.warning(
                "Could not copy group card %s to admin %s: %s",
                card.id,
                admin_id,
                copy_exc,
            )
    try:
        await bot.send_message(
            admin_id,
            format_card_preview(card),
            reply_markup=pending_card_keyboard(card.id),
        )
    except TelegramAPIError:
        return


async def publish_meeting_invite(bot: Bot, dest: ClubDestination, invite: MeetingInvite) -> None:
    document = BufferedInputFile(invite.ics_bytes, filename=invite.filename)
    await send_with_topic_fallback(
        lambda thread_id: bot.send_document(
            chat_id=dest.chat_id,
            document=document,
            caption=invite.caption,
            message_thread_id=thread_id,
            disable_content_type_detection=True,
        ),
        chat_id=dest.chat_id,
        message_thread_id=dest.message_thread_id,
        operation="Meeting invite",
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
    thread_id = dest.message_thread_id
    if send_intro:
        intro = meeting_date_runoff_intro() if runoff else meeting_poll_intro(title)
        _, thread_id = await send_with_topic_fallback(
            lambda current_thread_id: bot.send_message(
                dest.chat_id,
                intro,
                message_thread_id=current_thread_id,
            ),
            chat_id=dest.chat_id,
            message_thread_id=thread_id,
            operation="Meeting poll intro",
        )
    labels = option_labels(choices)
    poll_options: list[InputPollOption | str] = list(labels)
    message, _ = await send_with_topic_fallback(
        lambda current_thread_id: bot.send_poll(
            chat_id=dest.chat_id,
            question=meeting_date_runoff_question() if runoff else meeting_poll_question(title),
            options=poll_options,
            is_anonymous=False,
            allows_multiple_answers=not runoff,
            allow_adding_options=not runoff,
            message_thread_id=current_thread_id,
        ),
        chat_id=dest.chat_id,
        message_thread_id=thread_id,
        operation="Meeting date poll",
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


async def publish_meeting_time_poll(
    bot: Bot,
    dest: ClubDestination,
    title: str,
    choices: list[MeetingTimeOption],
    *,
    day: date | None = None,
    runoff: bool = False,
    send_intro: bool = True,
) -> PublishedMeetingTimePoll | None:
    thread_id = dest.message_thread_id
    if send_intro:
        intro = meeting_time_runoff_intro() if runoff else meeting_time_poll_intro(title, day)
        _, thread_id = await send_with_topic_fallback(
            lambda current_thread_id: bot.send_message(
                dest.chat_id,
                intro,
                message_thread_id=current_thread_id,
            ),
            chat_id=dest.chat_id,
            message_thread_id=thread_id,
            operation="Meeting time poll intro",
        )
    labels = option_labels(choices)
    poll_options: list[InputPollOption | str] = list(labels)
    message, _ = await send_with_topic_fallback(
        lambda current_thread_id: bot.send_poll(
            chat_id=dest.chat_id,
            question=(
                meeting_time_runoff_question()
                if runoff
                else meeting_time_poll_question(title)
            ),
            options=poll_options,
            is_anonymous=False,
            allows_multiple_answers=not runoff,
            allow_adding_options=False,
            message_thread_id=current_thread_id,
        ),
        chat_id=dest.chat_id,
        message_thread_id=thread_id,
        operation="Meeting time poll",
    )
    poll = message.poll
    if poll is None:
        return None
    return PublishedMeetingTimePoll(
        chat_id=dest.chat_id,
        message_id=message.message_id,
        telegram_poll_id=poll.id,
        option_hours=option_hours(choices),
    )


async def stop_meeting_time_polls(
    bot: Bot,
    polls: list[MeetingTimePoll],
) -> list[tuple[MeetingTimePoll, list[PollOption]]]:
    stopped: list[tuple[MeetingTimePoll, list[PollOption]]] = []
    for poll in polls:
        result = await bot.stop_poll(chat_id=poll.chat_id, message_id=poll.message_id)
        stopped.append((poll, list(result.options)))
    return stopped
