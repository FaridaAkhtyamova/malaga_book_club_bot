from __future__ import annotations

import asyncio
import logging

import httpx

from app.schemas.book import BookSchema
from app.services.google_books import normalize_cover_url
from app.services.http_client import async_http_client

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2
_BACKOFF_SECONDS = 0.4


class OpenLibraryError(Exception):
    """Raised when the Open Library request fails."""


class OpenLibraryService:
    SEARCH_URL = "https://openlibrary.org/search.json"
    COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
    MAX_RESULTS = 10

    async def search_books(self, query: str) -> list[BookSchema]:
        params: dict[str, str | int] = {"q": query, "limit": self.MAX_RESULTS}
        payload = await self._get_payload(params)
        docs = payload.get("docs") or []
        if not isinstance(docs, list):
            docs = []
        books: list[BookSchema] = []
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            key = doc.get("key")
            title = doc.get("title")
            if not isinstance(key, str) or not isinstance(title, str) or not title:
                continue

            work_id = key.rsplit("/", 1)[-1]
            raw_authors = doc.get("author_name") or []
            authors = [str(name) for name in raw_authors] if isinstance(raw_authors, list) else []
            cover_id = doc.get("cover_i")
            cover_url = None
            if isinstance(cover_id, int):
                cover_url = normalize_cover_url(self.COVER_URL.format(cover_id=cover_id))

            raw_pages = doc.get("number_of_pages_median")
            page_count = raw_pages if isinstance(raw_pages, int) else None
            description = _first_sentence(doc.get("first_sentence"))

            books.append(
                BookSchema(
                    title=title,
                    authors=authors,
                    description=description,
                    cover_url=cover_url,
                    google_id=f"ol-{work_id}",
                    page_count=page_count,
                )
            )

        return books

    async def _get_payload(self, params: dict[str, str | int]) -> dict[str, object]:
        last_error: httpx.HTTPError | None = None
        async with async_http_client(timeout=5.0) as client:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    response = await client.get(self.SEARCH_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if isinstance(payload, dict):
                        return payload
                    raise OpenLibraryError("Open Library request failed")
                except httpx.HTTPError as exc:
                    last_error = exc
                    logger.info(
                        "Open Library search failed (%s), attempt %s/%s",
                        type(exc).__name__,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    if attempt + 1 >= _MAX_ATTEMPTS:
                        break
                    await asyncio.sleep(_BACKOFF_SECONDS)

        logger.warning(
            "Open Library search failed: %s",
            type(last_error).__name__ if last_error else "unknown",
        )
        raise OpenLibraryError("Open Library request failed") from last_error


def _first_sentence(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None
