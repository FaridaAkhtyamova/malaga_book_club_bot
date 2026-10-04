from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.bot import club_publish
from app.bot.club_chat import send_html_card
from app.db.models import Book
from app.services.club_destination import ClubDestination
from app.services.meeting_invite import MeetingInvite
from app.services.meeting_poll import MeetingDateOption, MeetingTimeOption


def _thread_not_found() -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message="Bad Request: message thread not found")


def _message_without_poll() -> SimpleNamespace:
    return SimpleNamespace(message_id=1, poll=None)


async def test_send_html_card_retries_caption_without_missing_thread() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [_thread_not_found(), None]

    await send_html_card(bot, -100123, "Книга месяца", None, 456, parse_mode=None)

    assert [call.kwargs["message_thread_id"] for call in bot.send_message.await_args_list] == [
        456,
        None,
    ]


async def test_send_html_card_does_not_retry_other_bad_requests() -> None:
    bot = AsyncMock()
    error = TelegramBadRequest(method=MagicMock(), message="Bad Request: chat not found")
    bot.send_message.side_effect = error

    with pytest.raises(TelegramBadRequest, match="chat not found"):
        await send_html_card(bot, -100123, "Книга месяца", None, 456, parse_mode=None)

    bot.send_message.assert_awaited_once()


async def test_club_announcement_retries_without_missing_thread(monkeypatch) -> None:
    monkeypatch.setattr(club_publish, "suggest_dm_keyboard", AsyncMock(return_value=None))
    bot = AsyncMock()
    bot.send_message.side_effect = [_thread_not_found(), None]
    dest = ClubDestination(chat_id=-100123, message_thread_id=456)

    await club_publish.publish_club_announcement(bot, dest, "Сбор предложений открыт")

    assert [call.kwargs["message_thread_id"] for call in bot.send_message.await_args_list] == [
        456,
        None,
    ]


async def test_meeting_date_intro_fallback_uses_general_chat_for_poll() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [_thread_not_found(), None]
    bot.send_poll.return_value = _message_without_poll()
    dest = ClubDestination(chat_id=-100123, message_thread_id=456)

    await club_publish.publish_meeting_poll(
        bot,
        dest,
        "Книга",
        [MeetingDateOption("25 октября", datetime(2026, 10, 25).date())],
    )

    assert bot.send_poll.await_args.kwargs["message_thread_id"] is None


async def test_meeting_date_poll_retries_without_missing_thread() -> None:
    bot = AsyncMock()
    bot.send_message.return_value = None
    bot.send_poll.side_effect = [_thread_not_found(), _message_without_poll()]
    dest = ClubDestination(chat_id=-100123, message_thread_id=456)

    await club_publish.publish_meeting_poll(
        bot,
        dest,
        "Книга",
        [MeetingDateOption("25 октября", datetime(2026, 10, 25).date())],
    )

    assert [call.kwargs["message_thread_id"] for call in bot.send_poll.await_args_list] == [
        456,
        None,
    ]


async def test_vote_poll_retries_without_missing_thread(monkeypatch) -> None:
    monkeypatch.setattr(club_publish, "format_poll_option", lambda book, used: "Книга")
    bot = AsyncMock()
    bot.send_message.return_value = None
    bot.send_poll.side_effect = [_thread_not_found(), _message_without_poll()]
    cycle = SimpleNamespace(target_month=10)
    book = Book(id=1, title="Книга", google_id="book-1")
    dest = ClubDestination(chat_id=-100123, message_thread_id=456)

    await club_publish.publish_vote_polls(bot, dest, cycle, [[book]])

    assert [call.kwargs["message_thread_id"] for call in bot.send_poll.await_args_list] == [
        456,
        None,
    ]


async def test_vote_poll_partial_failure_stops_published_polls(monkeypatch) -> None:
    monkeypatch.setattr(club_publish, "format_poll_option", lambda book, used: book.title)
    bot = AsyncMock()
    bot.send_message.return_value = None
    first_poll = SimpleNamespace(
        message_id=101,
        poll=SimpleNamespace(id="poll-1"),
    )
    error = TelegramBadRequest(method=MagicMock(), message="poll failure")
    bot.send_poll.side_effect = [first_poll, error]
    cycle = SimpleNamespace(target_month=10)
    books = [
        Book(id=1, title="Книга 1", google_id="book-1"),
        Book(id=2, title="Книга 2", google_id="book-2"),
    ]
    dest = ClubDestination(chat_id=-100123, message_thread_id=None)

    with pytest.raises(TelegramBadRequest, match="poll failure"):
        await club_publish.publish_vote_polls(bot, dest, cycle, [[books[0]], [books[1]]])

    bot.stop_poll.assert_awaited_once_with(chat_id=-100123, message_id=101)


async def test_record_vote_polls_failure_rolls_back_and_stops_polls() -> None:
    service = SimpleNamespace(
        session=SimpleNamespace(rollback=AsyncMock()),
        record_vote_polls=AsyncMock(side_effect=RuntimeError("database failure")),
    )
    bot = AsyncMock()
    cycle = SimpleNamespace(id=1)
    poll = SimpleNamespace(chat_id=-100123, message_id=101)

    with pytest.raises(RuntimeError, match="database failure"):
        await club_publish.record_vote_polls_or_stop(bot, service, cycle, [poll])

    service.session.rollback.assert_awaited_once()
    bot.stop_poll.assert_awaited_once_with(chat_id=-100123, message_id=101)


async def test_meeting_time_poll_retries_without_missing_thread() -> None:
    bot = AsyncMock()
    bot.send_message.return_value = None
    bot.send_poll.side_effect = [_thread_not_found(), _message_without_poll()]
    dest = ClubDestination(chat_id=-100123, message_thread_id=456)

    await club_publish.publish_meeting_time_poll(
        bot,
        dest,
        "Книга",
        [MeetingTimeOption("19:00", 19)],
        send_intro=False,
    )

    assert [call.kwargs["message_thread_id"] for call in bot.send_poll.await_args_list] == [
        456,
        None,
    ]


async def test_meeting_invite_retries_without_missing_thread() -> None:
    bot = AsyncMock()
    bot.send_document.side_effect = [_thread_not_found(), None]
    dest = ClubDestination(chat_id=-100123, message_thread_id=456)
    invite = MeetingInvite(
        title="Книжный клуб",
        start=datetime(2026, 10, 25, 19),
        end=datetime(2026, 10, 25, 20, 30),
        ics_bytes=b"calendar",
        caption="Встреча клуба",
    )

    await club_publish.publish_meeting_invite(bot, dest, invite)

    assert [call.kwargs["message_thread_id"] for call in bot.send_document.await_args_list] == [
        456,
        None,
    ]


