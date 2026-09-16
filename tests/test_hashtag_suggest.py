from app.services.hashtag_suggest import parse_hashtag_suggestion


def test_parse_title_pages_and_description() -> None:
    parsed = parse_hashtag_suggestion(
        "#выбор_книги Имя Розы, 500\nДетектив про монастырь."
    )
    assert parsed is not None
    assert parsed.title == "Имя Розы"
    assert parsed.page_count == 500
    assert parsed.authors is None
    assert parsed.description == "Детектив про монастырь."


def test_parse_is_case_insensitive() -> None:
    parsed = parse_hashtag_suggestion("#Выбор_Книги Дюна 412")
    assert parsed is not None
    assert parsed.title == "Дюна"
    assert parsed.page_count == 412
    assert parsed.description is None


def test_parse_title_without_pages() -> None:
    parsed = parse_hashtag_suggestion("#выбор_книги Только название")
    assert parsed is not None
    assert parsed.title == "Только название"
    assert parsed.page_count is None


def test_parse_group_card() -> None:
    parsed = parse_hashtag_suggestion(
        "📖 #выбор_книги\n"
        "Имя Розы\n"
        "Умберто Эко\n"
        "объём страниц: 500\n"
        "Предложил(а): @ann\n"
        "\n"
        "Детектив про монастырь."
    )
    assert parsed is not None
    assert parsed.title == "Имя Розы"
    assert parsed.authors == "Умберто Эко"
    assert parsed.page_count == 500
    assert parsed.description == "Детектив про монастырь."


def test_parse_group_card_without_pages() -> None:
    parsed = parse_hashtag_suggestion(
        "#выбор_книги\n"
        "Дюна\n"
        "автор не указан\n"
        "объём страниц не указан\n"
        "Предложил(а): Анна"
    )
    assert parsed is not None
    assert parsed.title == "Дюна"
    assert parsed.authors is None
    assert parsed.page_count is None
    assert parsed.description is None


def test_parse_hashtag_only_has_no_title() -> None:
    parsed = parse_hashtag_suggestion("#выбор_книги")
    assert parsed is not None
    assert parsed.title is None
