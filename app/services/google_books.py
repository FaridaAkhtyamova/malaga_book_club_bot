from __future__ import annotations

import httpx

from app.schemas.book import BookSchema


class GoogleBooksService:
    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    async def search_books(self, query: str) -> list[BookSchema]:
        params = {"q": query}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        items = payload.get("items", [])
        books: list[BookSchema] = []

        for item in items:
            volume_info = item.get("volumeInfo", {})
            sale_info = item.get("saleInfo", {})

            book = BookSchema(
                title=volume_info.get("title") or "",
                authors=volume_info.get("authors") or [],
                description=volume_info.get("description"),
                cover_url=(
                    volume_info.get("imageLinks", {}).get("thumbnail")
                    if volume_info.get("imageLinks")
                    else None
                ),
                google_id=item.get("id") or "",
            )
            books.append(book)

        return books
