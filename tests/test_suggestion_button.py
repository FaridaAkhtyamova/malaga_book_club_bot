from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ReplyKeyboardRemove

from app.bot import club_publish
from app.bot.handlers import books
from app.repositories.suggestion_repo import SuggestionRepository


async def test_idle_text_starts_suggest_search(monkeypatch) -> None:
    message = AsyncMock()
    message.text = "  Дюна  "
    state = AsyncMock()
    session = AsyncMock()
    bot = AsyncMock()
    begin_suggest = AsyncMock()
    monkeypatch.setattr(books, "begin_suggest", begin_suggest)

    await books.process_idle_text_as_query(message, state, session, bot)

    begin_suggest.assert_awaited_once_with(
        message, state, session, bot, query="Дюна"
    )


async def test_suggestion_user_ids_are_selected_for_club() -> None:
    session = AsyncMock()
    result = Mock()
    result.scalars.return_value.all.return_value = [11, 22]
    session.execute.return_value = result

    user_ids = await SuggestionRepository(session).list_user_ids_for_club(7)

    assert user_ids == [11, 22]
    session.execute.assert_awaited_once()


@pytest.mark.parametrize("enabled", [True, False])
async def test_sync_suggestion_buttons_removes_reply_keyboard(monkeypatch, enabled: bool) -> None:
    repository = Mock()
    repository.list_user_ids_for_club = AsyncMock(return_value=[11, 22])
    monkeypatch.setattr(club_publish, "SuggestionRepository", lambda session: repository)
    bot = AsyncMock()

    await club_publish.sync_suggestion_buttons(bot, AsyncMock(), 7, enabled=enabled)

    assert [call.args[0] for call in bot.send_message.await_args_list] == [11, 22]
    markup = bot.send_message.await_args.kwargs["reply_markup"]
    assert isinstance(markup, ReplyKeyboardRemove)
    if enabled:
        assert "Отправьте название книги" in bot.send_message.await_args.args[1]


async def test_sync_suggestion_buttons_continues_after_dm_failure(monkeypatch) -> None:
    repository = Mock()
    repository.list_user_ids_for_club = AsyncMock(return_value=[11, 22])
    monkeypatch.setattr(club_publish, "SuggestionRepository", lambda session: repository)
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramForbiddenError(method=Mock(), message="bot was blocked"),
        None,
    ]

    await club_publish.sync_suggestion_buttons(bot, AsyncMock(), 7, enabled=True)

    assert bot.send_message.await_count == 2


