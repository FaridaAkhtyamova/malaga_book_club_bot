from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import admin
from app.bot.states.admin import ScheduleDayStates


@pytest.mark.asyncio
async def test_set_vote_day_accepts_follow_up_zero(monkeypatch) -> None:
    club = SimpleNamespace(id=8, vote_day=2, suggest_day=None)
    service = SimpleNamespace(set_vote_day=AsyncMock())
    service.set_vote_day.return_value = SimpleNamespace(vote_day=0)
    state = SimpleNamespace(update_data=AsyncMock(), set_state=AsyncMock())
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=21),
        text="/set_vote_day",
        answer=AsyncMock(),
    )
    session = object()
    bot = object()

    monkeypatch.setattr(admin, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(admin, "clubs_where_admin", AsyncMock(return_value=[club]))
    monkeypatch.setattr(admin, "CycleService", lambda *_: service)

    await admin.cmd_set_vote_day(
        message,
        SimpleNamespace(args=None),
        session,
        bot,
        state,
    )

    state.update_data.assert_awaited_once_with(
        schedule_day_kind="vote",
        schedule_day_club_id=club.id,
    )
    state.set_state.assert_awaited_once_with(ScheduleDayStates.waiting_day)

    message.text = "0"
    state.get_data = AsyncMock(
        return_value={
            "schedule_day_kind": "vote",
            "schedule_day_club_id": club.id,
        }
    )
    state.clear = AsyncMock()

    await admin.process_schedule_day(message, state, session, bot)

    service.set_vote_day.assert_awaited_once_with(0)
    state.clear.assert_awaited_once()
    assert "Автоматический запуск голосования отключён." in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_set_vote_day_accepts_zero_as_command_argument(monkeypatch) -> None:
    club = SimpleNamespace(id=8, vote_day=2, suggest_day=None)
    service = SimpleNamespace(set_vote_day=AsyncMock())
    service.set_vote_day.return_value = SimpleNamespace(vote_day=0)
    message = SimpleNamespace(answer=AsyncMock())

    monkeypatch.setattr(admin, "require_admin_club", AsyncMock(return_value=club))
    monkeypatch.setattr(admin, "CycleService", lambda *_: service)

    await admin.cmd_set_vote_day(
        message,
        SimpleNamespace(args="0"),
        object(),
        object(),
        AsyncMock(),
    )

    service.set_vote_day.assert_awaited_once_with(0)
    assert "Автоматический запуск голосования отключён." in message.answer.await_args.args[0]
