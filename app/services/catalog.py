from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from app.schemas.book import BookSchema
from app.services.google_books import GoogleBooksError, GoogleBooksService
from app.services.open_library import OpenLibraryError, OpenLibraryService

logger = logging.getLogger(__name__)

_DISPLAY_LIMIT = 5
_MIN_TOKEN_LEN = 2
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "of",
        "or",
        "to",
        "и",
        "в",
        "во",
        "на",
        "по",
        "с",
        "со",
        "о",
        "об",
        "от",
        "для",
        "из",
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "y",
        "un",
        "una",
    }
)

_google_books: GoogleBooksService | None = None
_open_library: OpenLibraryService | None = None


def _google() -> GoogleBooksService:
    global _google_books
    if _google_books is None:
        _google_books = GoogleBooksService()
    return _google_books


def _openlib() -> OpenLibraryService:
    global _open_library
    if _open_library is None:
        _open_library = OpenLibraryService()
    return _open_library


def _alnum_tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^\w]+", text.casefold()) if token]


def _normalized_text(text: str) -> str:
    return " ".join(_alnum_tokens(text))


def _significant_tokens(text: str) -> set[str]:
    return {
        token
        for token in _alnum_tokens(text)
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS
    }


def _completeness(book: BookSchema) -> int:
    has_cover = 1 if book.cover_url else 0
    has_description = 1 if (book.description or "").strip() else 0
    return has_cover + has_description


def _identity_key(book: BookSchema) -> tuple[str, tuple[str, ...]]:
    title = _normalized_text(book.title)
    authors = tuple(
        sorted(_normalized_text(name) for name in book.authors if _normalized_text(name))
    )
    return (title, authors)


def _match_score(query: str, book: BookSchema) -> tuple[int, int, int, int, int, int]:
    q_tokens = _significant_tokens(query)
    title_tokens = _significant_tokens(book.title)
    author_tokens = _significant_tokens(" ".join(book.authors))
    haystack = title_tokens | author_tokens
    query_norm = _normalized_text(query)
    title_norm = _normalized_text(book.title)
    exact_title = int(
        bool(query_norm)
        and (query_norm == title_norm or title_norm.startswith(f"{query_norm} "))
    )
    title_overlap = len(q_tokens & title_tokens)
    author_overlap = len(q_tokens & author_tokens)
    all_in_title = int(bool(q_tokens) and q_tokens <= title_tokens)
    all_in_record = int(bool(q_tokens) and q_tokens <= haystack)
    return (
        exact_title,
        all_in_title,
        all_in_record,
        title_overlap,
        author_overlap,
        _completeness(book),
    )


def _has_overlap(query: str, book: BookSchema) -> bool:
    q_tokens = _significant_tokens(query)
    if not q_tokens:
        return True
    haystack = _significant_tokens(book.title) | _significant_tokens(" ".join(book.authors))
    return bool(q_tokens & haystack)


def _dedupe_editions(books: Sequence[BookSchema]) -> list[BookSchema]:
    best: dict[tuple[str, tuple[str, ...]], BookSchema] = {}
    order: list[tuple[str, tuple[str, ...]]] = []
    for book in books:
        key = _identity_key(book)
        current = best.get(key)
        if current is None:
            best[key] = book
            order.append(key)
            continue
        if _completeness(book) > _completeness(current):
            best[key] = book
    return [best[key] for key in order]


def rank_catalog_results(query: str, books: list[BookSchema]) -> list[BookSchema]:
    unique = _dedupe_editions(books)
    scored = list(enumerate(unique))
    scored.sort(key=lambda item: (*_match_score(query, item[1]), -item[0]), reverse=True)
    ranked = [book for _, book in scored]
    overlapping = [book for book in ranked if _has_overlap(query, book)]
    chosen = overlapping if overlapping else ranked
    return chosen[:_DISPLAY_LIMIT]


async def search_catalog(query: str) -> list[BookSchema]:
    try:
        books = await _google().search_books(query)
        if books:
            return rank_catalog_results(query, books)
        logger.info("Google Books returned no results, trying Open Library")
    except GoogleBooksError:
        logger.warning("Google Books unavailable, trying Open Library")

    try:
        return rank_catalog_results(query, await _openlib().search_books(query))
    except OpenLibraryError:
        return []
