from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import club_setup
from app.bot.states.book_vote import WinnerCoverStates
from app.db.models import Book, SuggestionCycle
from app.services.vote_close import winner_announcement


def _book(cover_url: str | None) -> Book:
    return Book(
        id=41,
        title="Dune",
        authors="Frank Herbert",
        google_id="dune",
        cover_url=cover_url,
    )


def _close_vote_dependencies(monkeypatch, book: Book):
    club = SimpleNamespace(id=3, group_chat_id=-1003)
    destination = SimpleNamespace(chat_id=-1003, message_thread_id=None)
    cycle = SimpleNamespace(
        id=7,
        club_id=club.id,
        target_month=10,
        status=SuggestionCycle.STATUS_VOTING,
    )
    poll = object()
    service = SimpleNamespace(
        get_latest_voting=AsyncMock(return_value=cycle),
        require_open_vote_polls=AsyncMock(return_value=[poll]),
        mark_poll_closed=AsyncMock(),
        books_by_ids=AsyncMock(return_value=[book]),
        apply_winner=AsyncMock(),
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=destination.chat_id),
        message_thread_id=None,
        answer=AsyncMock(),
    )
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    bot = object()
    session = object()

    monkeypatch.setattr(club_setup, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(club_setup, "destination_of", lambda _: destination)
    monkeypatch.setattr(club_setup, "CycleService", lambda *_: service)
    monkeypatch.setattr(club_setup, "stop_vote_polls", AsyncMock(return_value={book.id: 1}))
    monkeypatch.setattr(club_setup, "publish_winner_announcement", AsyncMock())
    meeting_poll = AsyncMock()
    monkeypatch.setattr(club_setup, "publish_meeting_poll", meeting_poll)

    return (
        club,
        destination,
        cycle,
        service,
        message,
        state,
        meeting_poll,
        bot,
        session,
    )


@pytest.mark.asyncio
async def test_close_vote_publishes_winner_without_starting_meeting_poll(monkeypatch) -> None:
    book = _book("cover-id")
    (
        _,
        destination,
        cycle,
        service,
        message,
        state,
        meeting_poll,
        bot,
        session,
    ) = (
        _close_vote_dependencies(monkeypatch, book)
    )

    await club_setup.cmd_close_vote(message, session, bot, state)

    club_setup.publish_winner_announcement.assert_awaited_once_with(
        bot,
        destination,
        winner_announcement(cycle, book),
        "cover-id",
    )
    service.apply_winner.assert_awaited_once_with(cycle, book)
    meeting_poll.assert_not_awaited()
    state.set_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_vote_requests_cover_before_publishing_winner(monkeypatch) -> None:
    book = _book(None)
    (
        _,
        _,
        cycle,
        service,
        message,
        state,
        meeting_poll,
        bot,
        session,
    ) = _close_vote_dependencies(monkeypatch, book)

    await club_setup.cmd_close_vote(message, session, bot, state)

    service.apply_winner.assert_awaited_once_with(cycle, book)
    state.update_data.assert_awaited_once_with(
        winner_cover_club_id=3,
        winner_cover_cycle_id=cycle.id,
        winner_cover_book_id=book.id,
    )
    state.set_state.assert_awaited_once_with(WinnerCoverStates.waiting_photo)
    club_setup.publish_winner_announcement.assert_not_awaited()
    meeting_poll.assert_not_awaited()
    assert "Отправьте фото обложки" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_uploading_cover_saves_and_publishes_selected_book(monkeypatch) -> None:
    book = _book(None)
    club = SimpleNamespace(id=3, group_chat_id=-1003)
    destination = SimpleNamespace(chat_id=-1003, message_thread_id=None)
    cycle = SimpleNamespace(
        id=7,
        club_id=club.id,
        winner_book_id=book.id,
        target_month=10,
        status=SuggestionCycle.STATUS_CLOSED,
    )
    cycle_repo = SimpleNamespace(get=AsyncMock(return_value=cycle))
    service = SimpleNamespace(book_for_cycle=AsyncMock(return_value=book))

    async def save_cover(book_id: int, cover_id: str) -> Book:
        assert book_id == book.id
        book.cover_url = cover_id
        return book

    book_repo = SimpleNamespace(set_cover=AsyncMock(side_effect=save_cover))
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "winner_cover_club_id": club.id,
                "winner_cover_cycle_id": cycle.id,
                "winner_cover_book_id": book.id,
            }
        ),
        clear=AsyncMock(),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=11),
        answer=AsyncMock(),
    )
    bot = object()
    session = object()

    monkeypatch.setattr(club_setup, "CycleRepository", lambda _: cycle_repo)
    monkeypatch.setattr(club_setup, "clubs_where_admin", AsyncMock(return_value=[club]))
    monkeypatch.setattr(club_setup, "CycleService", lambda *_: service)
    monkeypatch.setattr(club_setup, "BookRepository", lambda _: book_repo)
    monkeypatch.setattr(club_setup, "cover_file_id", lambda _: "uploaded-cover")
    monkeypatch.setattr(club_setup, "destination_of", lambda _: destination)
    monkeypatch.setattr(club_setup, "publish_winner_announcement", AsyncMock())
    meeting_poll = AsyncMock()
    monkeypatch.setattr(club_setup, "publish_meeting_poll", meeting_poll)

    await club_setup.process_winner_cover(message, state, session, bot)

    book_repo.set_cover.assert_awaited_once_with(book.id, "uploaded-cover")
    club_setup.publish_winner_announcement.assert_awaited_once_with(
        bot,
        destination,
        winner_announcement(cycle, book),
        "uploaded-cover",
    )
    state.clear.assert_awaited_once()
    meeting_poll.assert_not_awaited()
