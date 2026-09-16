from app.services.hashtag_suggest import parse_hashtag_suggestion


def test_parse_title_pages_and_description() -> None:
    parsed = parse_hashtag_suggestion(
        "#выбор_книги Имя Розы, 500\nДетектив про монастырь."
    )
    assert parsed is not None
    assert parsed.title == "Имя Розы"
    assert parsed.page_count == 500
    assert parsed.description == "Детектив про монастырь."


def test_parse_is_case_insensitive() -> None:
    parsed = parse_hashtag_suggestion("#Выбор_Книги Дюна 412")
    assert parsed is not None
    assert parsed.title == "Дюна"
    assert parsed.page_count == 412
    assert parsed.description is None


def test_parse_rejects_missing_pages() -> None:
    assert parse_hashtag_suggestion("#выбор_книги Только название") is None
