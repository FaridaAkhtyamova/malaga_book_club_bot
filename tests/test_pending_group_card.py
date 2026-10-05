from unittest.mock import AsyncMock

from app.db.models import PendingGroupCard, SuggestionCycle
from app.services.cycle_service import PendingGroupCardsNeedReviewError
from app.services.hashtag_suggest import parse_hashtag_suggestion
from app.services.pending_group_card import PendingGroupCardService, format_card_preview


def _card(**kwargs: object) -> PendingGroupCard:
    values: dict[str, object] = {
        "id": 1,
        "cycle_id": 1,
        "chat_id": -100,
        "message_id": 10,
        "user_id": 42,
        "raw_text": "#выбор_книги",
        "title": None,
        "authors": None,
        "description": None,
        "page_count": None,
        "status": PendingGroupCard.STATUS_PENDING,
    }
    values.update(kwargs)
    return PendingGroupCard(**values)  # type: ignore[arg-type]


def test_preview_marks_unparsed_title() -> None:
    text = format_card_preview(_card())
    assert "не распознано" in text


def test_preview_uses_parsed_fields() -> None:
    parsed = parse_hashtag_suggestion("#выбор_книги Имя Розы, 500\nДетектив")
    assert parsed is not None
    text = format_card_preview(
        _card(
            title=parsed.title,
            authors=parsed.authors,
            description=parsed.description,
            page_count=parsed.page_count,
        )
    )
    assert "Имя Розы" in text
    assert "500" in text


def test_pending_review_blocks_vote_message() -> None:
    error = PendingGroupCardsNeedReviewError([_card()])
    assert "личке" in str(error)
    assert error.cards[0].id == 1


async def test_edit_without_hashtag_rejects_pending_card() -> None:
    service = PendingGroupCardService(None)  # type: ignore[arg-type]
    service.card_repo.get_by_source = AsyncMock(return_value=_card())
    service.card_repo.claim = AsyncMock(return_value=_card(status=PendingGroupCard.STATUS_REJECTED))

    removed = await service.remove_suggestion_from_edit(-100, 10)

    assert removed is True
    service.card_repo.claim.assert_awaited_once_with(1, PendingGroupCard.STATUS_REJECTED)


async def test_edit_without_hashtag_removes_approved_book() -> None:
    card = _card(
        status=PendingGroupCard.STATUS_APPROVED,
        approved_book_id=7,
    )
    cycle = SuggestionCycle(id=1, status=SuggestionCycle.STATUS_SUGGESTING)
    service = PendingGroupCardService(None)  # type: ignore[arg-type]
    service.card_repo.get_by_source = AsyncMock(return_value=card)
    service.cycle_repo.get = AsyncMock(return_value=cycle)
    service.suggestion_repo.remove = AsyncMock(return_value=True)

    removed = await service.remove_suggestion_from_edit(-100, 10)

    assert removed is True
    service.suggestion_repo.remove.assert_awaited_once_with(1, 7)


async def test_edit_does_not_remove_preexisting_suggestion() -> None:
    card = _card(status=PendingGroupCard.STATUS_APPROVED, approved_book_id=None)
    service = PendingGroupCardService(None)  # type: ignore[arg-type]
    service.card_repo.get_by_source = AsyncMock(return_value=card)
    service.cycle_repo.get = AsyncMock()

    removed = await service.remove_suggestion_from_edit(-100, 10)

    assert removed is False
    service.cycle_repo.get.assert_not_awaited()
