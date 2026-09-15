from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import get_settings
from app.schemas.book import BookSchema
from app.services.http_client import async_http_client

logger = logging.getLogger(__name__)

_RETRY_STATUSES = frozenset({429, 502, 503, 504})
_MAX_ATTEMPTS = 2
_BACKOFF_SECONDS = (0.3,)


def normalize_cover_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://"):
        return f"https://{url[7:]}"
    return url


class GoogleBooksError(Exception):
    """Raised when the Google Books API request fails."""


class GoogleBooksRateLimitError(GoogleBooksError):
    """Raised when Google Books returns HTTP 429."""


class GoogleBooksService:
    BASE_URL = "https://www.googleapis.com/books/v1/volumes"
    MAX_RESULTS = 10

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key else get_settings().GOOGLE_BOOKS_API_KEY

    async def search_books(self, query: str) -> list[BookSchema]:
        base_params: dict[str, str | int] = {"q": query, "maxResults": self.MAX_RESULTS}
        param_sets: list[dict[str, str | int]] = []
        if self.api_key:
            param_sets.append({**base_params, "key": self.api_key})
        param_sets.append(base_params)

        payload: dict[str, object] | None = None
        last_error: GoogleBooksError | None = None
        for index, params in enumerate(param_sets):
            try:
                payload = await self._get_payload(params)
                break
            except GoogleBooksError as exc:
                last_error = exc
                if index + 1 < len(param_sets):
                    logger.info("Google Books with API key failed, retrying without key")
                    continue
                raise

        if payload is None:
            raise last_error or GoogleBooksError("Google Books API request failed")

        raw_items = payload.get("items") or []
        items = raw_items if isinstance(raw_items, list) else []
        books: list[BookSchema] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            volume_info = item.get("volumeInfo") or {}
            if not isinstance(volume_info, dict):
                continue
            google_id = item.get("id")
            title = volume_info.get("title")
            if not isinstance(google_id, str) or not isinstance(title, str) or not title:
                continue

            image_links = volume_info.get("imageLinks") or {}
            if not isinstance(image_links, dict):
                image_links = {}
            raw_page_count = volume_info.get("pageCount")
            page_count = raw_page_count if isinstance(raw_page_count, int) else None
            raw_authors = volume_info.get("authors") or []
            authors = [str(name) for name in raw_authors] if isinstance(raw_authors, list) else []
            description = volume_info.get("description")
            thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail")
            cover = thumbnail if isinstance(thumbnail, str) else None
            books.append(
                BookSchema(
                    title=title,
                    authors=authors,
                    description=description if isinstance(description, str) else None,
                    cover_url=normalize_cover_url(cover),
                    google_id=google_id,
                    page_count=page_count,
                )
            )

        return books

    async def _get_payload(self, params: dict[str, str | int]) -> dict[str, object]:
        last_status: int | None = None
        async with async_http_client(timeout=5.0) as client:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    response = await client.get(self.BASE_URL, params=params)
                except httpx.HTTPError as exc:
                    logger.info(
                        "Google Books request failed (%s), attempt %s/%s",
                        type(exc).__name__,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    if attempt + 1 >= _MAX_ATTEMPTS:
                        raise GoogleBooksError("Google Books API request failed") from exc
                    await asyncio.sleep(_BACKOFF_SECONDS[0])
                    continue

                if response.status_code in _RETRY_STATUSES:
                    last_status = response.status_code
                    logger.info(
                        "Google Books HTTP %s, attempt %s/%s",
                        response.status_code,
                        attempt + 1,
                        _MAX_ATTEMPTS,
                    )
                    if attempt + 1 >= _MAX_ATTEMPTS:
                        break
                    await asyncio.sleep(_BACKOFF_SECONDS[0])
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    logger.warning("Google Books search failed: HTTP %s", exc.response.status_code)
                    if exc.response.status_code == 429:
                        raise GoogleBooksRateLimitError("Google Books rate limit exceeded") from exc
                    raise GoogleBooksError("Google Books API request failed") from exc

                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                raise GoogleBooksError("Google Books API request failed")

        if last_status == 429:
            raise GoogleBooksRateLimitError("Google Books rate limit exceeded")
        raise GoogleBooksError("Google Books API request failed")
