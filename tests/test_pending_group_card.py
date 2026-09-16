from app.db.models import PendingGroupCard
from app.services.cycle_service import PendingGroupCardsNeedReviewError
from app.services.hashtag_suggest import parse_hashtag_suggestion
from app.services.pending_group_card import format_card_preview


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
