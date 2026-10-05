from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import club_setup
from app.bot.states.suggestion import RemoveSuggestionStates


def _message(text: str = "", user_id: int = 42) -> AsyncMock:
    message = AsyncMock()
    message.text = text
    message.from_user = SimpleNamespace(id=user_id)
    return message


@pytest.mark.asyncio
async def test_remove_suggestion_command_prompts_for_next_message(monkeypatch) -> None:
    club = SimpleNamespace(id=7)
    require_admin_club = AsyncMock(return_value=club)
    monkeypatch.setattr(club_setup, "require_admin_club", require_admin_club)
    message = _message("/remove_suggestion")
    state = AsyncMock()

    await club_setup.cmd_remove_suggestion(message, state, AsyncMock(), AsyncMock())

    state.update_data.assert_awaited_once_with(remove_suggestion_club_id=7)
    state.set_state.assert_awaited_once_with(RemoveSuggestionStates.waiting_book_id)
    assert "ID" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_remove_suggestion_input_removes_book_and_finishes(monkeypatch) -> None:
    club = SimpleNamespace(id=7)
    service = SimpleNamespace(remove_suggestion=AsyncMock(return_value=True))
    monkeypatch.setattr(club_setup, "clubs_where_admin", AsyncMock(return_value=[club]))
    monkeypatch.setattr(
        club_setup,
        "SettingsRepository",
        lambda session: SimpleNamespace(get=AsyncMock(return_value=club)),
    )
    monkeypatch.setattr(club_setup, "CycleService", lambda session, selected: service)
    message = _message("123")
    state = AsyncMock()
    state.get_data.return_value = {"remove_suggestion_club_id": 7}

    await club_setup.on_remove_suggestion_book_id(message, state, AsyncMock(), AsyncMock())

    service.remove_suggestion.assert_awaited_once_with(123)
    state.clear.assert_awaited_once()
    assert "удалена" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_remove_suggestion_invalid_id_keeps_waiting(monkeypatch) -> None:
    message = _message("book one")
    state = AsyncMock()
    clubs_where_admin = AsyncMock()
    monkeypatch.setattr(club_setup, "clubs_where_admin", clubs_where_admin)

    await club_setup.on_remove_suggestion_book_id(message, state, AsyncMock(), AsyncMock())

    state.clear.assert_not_awaited()
    clubs_where_admin.assert_not_awaited()
    assert "числовой ID" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_remove_suggestion_not_found_keeps_waiting(monkeypatch) -> None:
    club = SimpleNamespace(id=7)
    service = SimpleNamespace(remove_suggestion=AsyncMock(return_value=False))
    monkeypatch.setattr(club_setup, "clubs_where_admin", AsyncMock(return_value=[club]))
    monkeypatch.setattr(
        club_setup,
        "SettingsRepository",
        lambda session: SimpleNamespace(get=AsyncMock(return_value=club)),
    )
    monkeypatch.setattr(club_setup, "CycleService", lambda session, selected: service)
    message = _message("123")
    state = AsyncMock()
    state.get_data.return_value = {"remove_suggestion_club_id": 7}

    await club_setup.on_remove_suggestion_book_id(message, state, AsyncMock(), AsyncMock())

    state.clear.assert_not_awaited()
    assert "нет" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_remove_suggestion_rechecks_admin_for_pinned_club(monkeypatch) -> None:
    another_club = SimpleNamespace(id=8)
    clubs_where_admin = AsyncMock(return_value=[another_club])
    monkeypatch.setattr(club_setup, "clubs_where_admin", clubs_where_admin)
    message = _message("123")
    state = AsyncMock()
    state.get_data.return_value = {"remove_suggestion_club_id": 7}

    await club_setup.on_remove_suggestion_book_id(message, state, AsyncMock(), AsyncMock())

    state.clear.assert_awaited_once()
    assert "прав" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cancel_remove_suggestion_clears_state() -> None:
    message = _message("/cancel")
    state = AsyncMock()

    await club_setup.cmd_cancel_remove_suggestion(message, state)

    state.clear.assert_awaited_once()
    assert "отменено" in message.answer.await_args.args[0]