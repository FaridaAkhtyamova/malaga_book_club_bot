from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.callbacks.meeting import MeetingInviteChoiceCallback
from app.bot.handlers import meeting
from app.bot.states.meeting import MeetingInviteStates


class _CallbackMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=1)
        self.message_thread_id = None
        self.answer = AsyncMock()
        self.edit_reply_markup = AsyncMock()


@pytest.mark.asyncio
async def test_create_meeting_offers_selected_topic_or_other_meeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    selected_day = date(2099, 12, 31)
    service = SimpleNamespace(
        get_selected_meeting=AsyncMock(return_value=("Dune", selected_day, 19))
    )
    state = AsyncMock()
    message = SimpleNamespace(answer=AsyncMock())

    monkeypatch.setattr(meeting, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(meeting, "remember_club", AsyncMock())
    monkeypatch.setattr(meeting, "destination_of", lambda _: destination)
    monkeypatch.setattr(meeting, "CycleService", lambda *_: service)

    await meeting.cmd_create_meeting(message, AsyncMock(), state, AsyncMock())

    state.update_data.assert_awaited_once_with(
        meeting_mode="cycle",
        book_title="Dune",
        meeting_date=selected_day.isoformat(),
        meeting_hour=19,
    )
    state.set_state.assert_awaited_once_with(MeetingInviteStates.waiting_choice)
    response = message.answer.await_args
    assert response is not None
    assert "выбранной темы" in response.args[0]
    keyboard = response.kwargs["reply_markup"]
    assert [button.text for row in keyboard.inline_keyboard for button in row] == [
        "По выбранной теме",
        "Другая встреча",
    ]


@pytest.mark.asyncio
async def test_create_meeting_without_selected_title_starts_fresh_other_meeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    service = SimpleNamespace(
        get_selected_meeting=AsyncMock(return_value=(None, date(2099, 12, 31), 19))
    )
    state = AsyncMock()
    message = SimpleNamespace(answer=AsyncMock())

    monkeypatch.setattr(meeting, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(meeting, "remember_club", AsyncMock())
    monkeypatch.setattr(meeting, "destination_of", lambda _: destination)
    monkeypatch.setattr(meeting, "CycleService", lambda *_: service)

    await meeting.cmd_create_meeting(message, AsyncMock(), state, AsyncMock())

    assert state.update_data.await_args_list[-1].kwargs == {
        "meeting_mode": "other",
        "book_title": None,
        "meeting_date": None,
        "meeting_hour": None,
    }
    state.set_state.assert_awaited_once_with(MeetingInviteStates.waiting_title)
    assert "название встречи" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_manual_meeting_title_does_not_load_cycle_date_or_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    service_factory = MagicMock()
    state = AsyncMock()
    state.get_data.return_value = {
        "meeting_mode": "other",
        "book_title": None,
        "meeting_date": None,
        "meeting_hour": None,
    }
    message = SimpleNamespace(text="Board games", answer=AsyncMock())

    monkeypatch.setattr(meeting, "club_from_state", AsyncMock(return_value=club))
    monkeypatch.setattr(meeting, "destination_of", lambda _: destination)
    monkeypatch.setattr(meeting, "CycleService", service_factory)

    await meeting.on_meeting_title(message, AsyncMock(), state, AsyncMock())

    service_factory.assert_not_called()
    state.set_state.assert_awaited_once_with(MeetingInviteStates.waiting_date)
    assert "25.09" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_manual_meeting_date_does_not_update_or_reuse_cycle_poll_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    service = SimpleNamespace(
        get_latest_cycle=AsyncMock(),
        apply_meeting_date=AsyncMock(),
        get_selected_meeting=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data.return_value = {
        "meeting_mode": "other",
        "book_title": "Board games",
        "meeting_date": None,
        "meeting_hour": None,
    }
    message = SimpleNamespace(text="31.12.2099", answer=AsyncMock())

    monkeypatch.setattr(meeting, "club_from_state", AsyncMock(return_value=club))
    monkeypatch.setattr(meeting, "remember_club", AsyncMock())
    monkeypatch.setattr(meeting, "destination_of", lambda _: destination)
    monkeypatch.setattr(meeting, "CycleService", lambda *_: service)

    await meeting.on_meeting_date(message, AsyncMock(), state, AsyncMock())

    service.get_latest_cycle.assert_not_awaited()
    service.apply_meeting_date.assert_not_awaited()
    service.get_selected_meeting.assert_not_awaited()
    state.set_state.assert_awaited_once_with(MeetingInviteStates.waiting_time)
    assert "Board games" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_other_meeting_choice_clears_cycle_title_date_and_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    message = _CallbackMessage()
    callback = SimpleNamespace(
        message=message,
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )
    state = AsyncMock()

    monkeypatch.setattr(meeting, "Message", _CallbackMessage)
    monkeypatch.setattr(meeting, "club_from_state", AsyncMock(return_value=club))
    monkeypatch.setattr(meeting, "clubs_where_admin", AsyncMock(return_value=[club]))
    monkeypatch.setattr(meeting, "destination_of", lambda _: destination)

    await meeting.on_meeting_invite_choice(
        callback,
        MeetingInviteChoiceCallback(action="other"),
        AsyncMock(),
        state,
        AsyncMock(),
    )

    assert state.update_data.await_args.kwargs == {
        "meeting_mode": "other",
        "book_title": None,
        "meeting_date": None,
        "meeting_hour": None,
    }
    state.set_state.assert_awaited_once_with(MeetingInviteStates.waiting_title)
    response = message.answer.await_args
    assert response is not None
    assert "название встречи" in response.args[0]
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_selected_meeting_choice_uses_saved_poll_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    club = SimpleNamespace(id=7)
    destination = SimpleNamespace(chat_id=-1007, message_thread_id=None)
    message = _CallbackMessage()
    callback = SimpleNamespace(
        message=message,
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data.return_value = {
        "meeting_mode": "cycle",
        "book_title": "Dune",
        "meeting_date": "2099-12-31",
        "meeting_hour": None,
    }

    monkeypatch.setattr(meeting, "Message", _CallbackMessage)
    monkeypatch.setattr(meeting, "club_from_state", AsyncMock(return_value=club))
    monkeypatch.setattr(meeting, "clubs_where_admin", AsyncMock(return_value=[club]))
    monkeypatch.setattr(meeting, "destination_of", lambda _: destination)

    await meeting.on_meeting_invite_choice(
        callback,
        MeetingInviteChoiceCallback(action="selected"),
        AsyncMock(),
        state,
        AsyncMock(),
    )

    state.set_state.assert_awaited_once_with(MeetingInviteStates.waiting_time)
    response = message.answer.await_args
    assert response is not None
    assert "Dune" in response.args[0]
    assert "31 декабря" in response.args[0]
    callback.answer.assert_awaited_once()
