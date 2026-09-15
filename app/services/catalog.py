from __future__ import annotations

import logging

from app.schemas.book import BookSchema
from app.services.google_books import GoogleBooksError, GoogleBooksService
from app.services.open_library import OpenLibraryError, OpenLibraryService

logger = logging.getLogger(__name__)

_DISPLAY_LIMIT = 5
_google_books = GoogleBooksService()
_open_library = OpenLibraryService()


def _result_rank(book: BookSchema) -> tuple[int, int, int]:
    has_cover = 1 if book.cover_url else 0
    has_description = 1 if (book.description or "").strip() else 0
    return (has_cover and has_description, has_cover, has_description)


def _prefer_complete_books(books: list[BookSchema]) -> list[BookSchema]:
    ranked = sorted(books, key=_result_rank, reverse=True)
    return ranked[:_DISPLAY_LIMIT]


async def search_catalog(query: str) -> list[BookSchema]:
    try:
        books = await _google_books.search_books(query)
        if books:
            return _prefer_complete_books(books)
        logger.info("Google Books returned no results, trying Open Library")
    except GoogleBooksError:
        logger.warning("Google Books unavailable, trying Open Library")

    try:
        return _prefer_complete_books(await _open_library.search_books(query))
    except OpenLibraryError:
        return []
