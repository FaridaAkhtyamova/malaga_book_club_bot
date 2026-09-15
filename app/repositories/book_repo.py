from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book
from app.schemas.book import BookSchema


class BookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_ids(self, ids: Sequence[int]) -> list[Book]:
        if not ids:
            return []
        result = await self.session.execute(select(Book).where(Book.id.in_(list(ids))))
        by_id = {book.id: book for book in result.scalars().all()}
        return [by_id[book_id] for book_id in ids if book_id in by_id]

    async def get_by_google_id(self, google_id: str) -> Book | None:
        result = await self.session.execute(select(Book).where(Book.google_id == google_id))
        return result.scalar_one_or_none()

    async def get_or_create(self, book: BookSchema) -> Book:
        existing = await self.get_by_google_id(book.google_id)
        if existing is not None:
            updated = False
            if existing.page_count is None and book.page_count is not None:
                existing.page_count = book.page_count
                updated = True
            if existing.cover_url is None and book.cover_url:
                existing.cover_url = book.cover_url[:500]
                updated = True
            if existing.description is None and book.description:
                existing.description = book.description
                updated = True
            if updated:
                await self.session.commit()
                await self.session.refresh(existing)
            return existing

        authors = ", ".join(book.authors)[:500] if book.authors else None
        entity = Book(
            title=book.title[:255],
            authors=authors,
            description=book.description,
            cover_url=book.cover_url[:500] if book.cover_url else None,
            google_id=book.google_id,
            page_count=book.page_count,
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def create_manual(
        self,
        *,
        title: str,
        authors: str | None,
        description: str | None,
        page_count: int | None,
    ) -> Book:
        entity = Book(
            title=title[:255],
            authors=authors[:500] if authors else None,
            description=description,
            cover_url=None,
            google_id=f"manual-{uuid4().hex}",
            page_count=page_count,
        )
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity
