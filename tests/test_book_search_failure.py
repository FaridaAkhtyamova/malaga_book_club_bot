from unittest.mock import AsyncMock

from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers import books
from app.services.catalog import CatalogSearchUnavailable


async def test_unavailable_search_offers_retry_and_manual_entry(monkeypatch) -> None:
    message = AsyncMock()
    message.from_user.full_name = "Reader"
    state = AsyncMock()
    search_catalog = AsyncMock(side_effect=CatalogSearchUnavailable())
    monkeypatch.setattr(books, "search_catalog", search_catalog)

    await books._search_and_show(message, state, "Дюна")

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "попробуйте позже" in text
    assert "вручную" in text
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = markup.inline_keyboard
    assert [button.text for row in buttons for button in row] == [
        "Поискать ещё раз",
        "Добавить книгу вручную",
    ]
    assert search_catalog.await_args.args == ("Дюна",)