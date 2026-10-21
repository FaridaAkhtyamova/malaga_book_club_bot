from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import club_setup
from app.services.meeting_poll import meeting_date_announcement


@pytest.mark.asyncio
async def test_entered_meeting_title_does_not_create_a_month_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    cycle = SimpleNamespace(id=3, target_month=10, meeting_title=None)
    service = SimpleNamespace(
        prepare_meeting_poll=AsyncMock(return_value=cycle),
        apply_meeting_title=AsyncMock(),
        book_for_cycle=AsyncMock(return_value=None),
    )
    state = AsyncMock()
    message = SimpleNamespace(text="Board games", answer=AsyncMock())

    monkeypatch.setattr(club_setup, "club_from_state", AsyncMock(return_value=club))
    monkeypatch.setattr(club_setup, "destination_of", lambda _: destination)
    monkeypatch.setattr(club_setup, "CycleService", lambda *_: service)
    monkeypatch.setattr(club_setup, "_finish_meeting_poll", AsyncMock())

    await club_setup.on_meeting_poll_title(message, AsyncMock(), state, AsyncMock())

    service.apply_meeting_title.assert_awaited_once_with(cycle, "Board Games")
    service.book_for_cycle.assert_awaited_once_with(cycle)
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_alternate_book_date_poll_does_not_save_date_to_month_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    cycle = SimpleNamespace(
        id=3,
        target_month=10,
        meeting_title="Board games",
        winner_meeting_date=None,
    )
    poll = SimpleNamespace(option_dates=["2026-10-25"])
    book = SimpleNamespace(title="Dune")
    service = SimpleNamespace(
        get_meeting_poll_cycle=AsyncMock(return_value=cycle),
        require_open_meeting_polls=AsyncMock(return_value=[poll]),
        book_for_cycle=AsyncMock(return_value=book),
        mark_meeting_poll_closed=AsyncMock(),
        apply_meeting_date=AsyncMock(),
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=destination.chat_id),
        message_thread_id=None,
        answer=AsyncMock(),
    )
    bot = object()

    monkeypatch.setattr(club_setup, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(club_setup, "destination_of", lambda _: destination)
    monkeypatch.setattr(club_setup, "CycleService", lambda *_: service)
    monkeypatch.setattr(
        club_setup,
        "stop_meeting_polls",
        AsyncMock(return_value=[(poll, [SimpleNamespace(voter_count=3)])]),
    )
    publish_announcement = AsyncMock()
    monkeypatch.setattr(club_setup, "publish_winner_announcement", publish_announcement)
    notify_admins = AsyncMock()
    monkeypatch.setattr(club_setup, "notify_admins", notify_admins)

    await club_setup.cmd_close_meeting_poll(message, AsyncMock(), bot)

    service.apply_meeting_date.assert_not_awaited()
    announced = publish_announcement.await_args.args[2]
    assert announced == meeting_date_announcement(cycle, book, date(2026, 10, 25))
    assert "Board games" in announced
    assert "Board games" in notify_admins.await_args.args[1]


@pytest.mark.asyncio
async def test_reset_meeting_date_command_clears_month_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    cycle = SimpleNamespace(id=3)
    service = SimpleNamespace(
        get_latest_cycle=AsyncMock(return_value=cycle),
        reset_month_meeting_date=AsyncMock(return_value=True),
    )
    message = SimpleNamespace(answer=AsyncMock())

    monkeypatch.setattr(club_setup, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(club_setup, "CycleService", lambda *_: service)

    await club_setup.cmd_reset_meeting_date(message, AsyncMock(), AsyncMock())

    service.reset_month_meeting_date.assert_awaited_once_with(cycle)
    assert "сброшена" in message.answer.await_args.args[0]


def test_month_date_announcement_is_not_replaced_by_an_alternate_title() -> None:
    cycle = SimpleNamespace(
        target_month=10,
        meeting_title="Board games",
    )
    book = SimpleNamespace(title="Dune")

    assert "Board games" in meeting_date_announcement(cycle, book, date(2026, 10, 25))
