from unittest.mock import AsyncMock

import pytest

from app.schemas.book import BookSchema
from app.services import catalog
from app.services.catalog import CatalogSearchUnavailable, rank_catalog_results
from app.services.google_books import GoogleBooksError, build_google_query
from app.services.open_library import OpenLibraryError


def _book(
    google_id: str,
    title: str,
    authors: list[str] | None = None,
    *,
    description: str | None = None,
    cover_url: str | None = None,
) -> BookSchema:
    return BookSchema(
        title=title,
        authors=authors or [],
        description=description,
        cover_url=cover_url,
        google_id=google_id,
        page_count=None,
    )


def test_build_google_query_wraps_title() -> None:
    assert build_google_query("Мастер и Маргарита") == 'intitle:"Мастер и Маргарита"'


def test_build_google_query_splits_title_and_author() -> None:
    assert (
        build_google_query("1984 - George Orwell")
        == 'intitle:"1984" inauthor:"George Orwell"'
    )


def test_build_google_query_detects_isbn() -> None:
    assert build_google_query("978-0-14-103614-4") == "isbn:9780141036144"


def test_title_match_beats_complete_unrelated_card() -> None:
    noise = _book(
        "noise",
        "How to Read Literature",
        ["Random"],
        description="A long essay that mentions 1984 in passing.",
        cover_url="https://example.com/cover.jpg",
    )
    hit = _book("hit", "1984", ["George Orwell"])
    ranked = rank_catalog_results("1984", [noise, hit])
    assert ranked[0].google_id == "hit"


def test_dedupes_editions_keeping_richer_card() -> None:
    thin = _book("thin", "Дюна", ["Фрэнк Герберт"])
    rich = _book(
        "rich",
        "Дюна",
        ["Фрэнк Герберт"],
        description="Пустыня.",
        cover_url="https://example.com/dune.jpg",
    )
    ranked = rank_catalog_results("Дюна", [thin, rich])
    assert [book.google_id for book in ranked] == ["rich"]


def test_drops_results_without_query_overlap() -> None:
    hit = _book("hit", "Мастер и Маргарита", ["Булгаков"])
    miss = _book(
        "miss",
        "Совершенно другая книга",
        ["Кто-то"],
        description="Обложка и текст есть.",
        cover_url="https://example.com/x.jpg",
    )
    ranked = rank_catalog_results("Мастер и Маргарита", [miss, hit])
    assert [book.google_id for book in ranked] == ["hit"]


async def test_search_catalog_raises_when_all_providers_are_unavailable(monkeypatch) -> None:
    google = AsyncMock()
    google.search_books.side_effect = GoogleBooksError("unavailable")
    open_library = AsyncMock()
    open_library.search_books.side_effect = OpenLibraryError("unavailable")
    monkeypatch.setattr(catalog, "_google", lambda: google)
    monkeypatch.setattr(catalog, "_openlib", lambda: open_library)

    with pytest.raises(CatalogSearchUnavailable):
        await catalog.search_catalog("Дюна")


async def test_search_catalog_keeps_empty_result_when_provider_responds(monkeypatch) -> None:
    google = AsyncMock()
    google.search_books.side_effect = GoogleBooksError("unavailable")
    open_library = AsyncMock()
    open_library.search_books.return_value = []
    monkeypatch.setattr(catalog, "_google", lambda: google)
    monkeypatch.setattr(catalog, "_openlib", lambda: open_library)

    assert await catalog.search_catalog("Дюна") == []
