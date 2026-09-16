from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book, User
from app.repositories.book_repo import BookRepository
from app.repositories.cycle_repo import CycleRepository
from app.repositories.suggestion_repo import SuggestionRepository
from app.services.cycle_service import CycleNotOpenError


class ManualBookService:
    def __init__(self, session: AsyncSession) -> None:
        self.cycle_repo = CycleRepository(session)
        self.suggestion_repo = SuggestionRepository(session)
        self.book_repo = BookRepository(session)

    async def add(
        self,
        user: User,
        *,
        title: str,
        authors: str | None,
        description: str | None,
        page_count: int | None,
        cover_url: str | None = None,
    ) -> tuple[Book, bool]:
        cycle = await self.cycle_repo.get_latest_suggesting()
        if cycle is None:
            raise CycleNotOpenError("Предложения ещё не открыты.")

        needle = title.casefold()
        for existing in await self.suggestion_repo.list_books(cycle.id):
            if existing.title.casefold() == needle:
                if cover_url and existing.cover_url is None:
                    existing.cover_url = cover_url[:500]
                    await self.session.commit()
                    await self.session.refresh(existing)
                return existing, False

        book = await self.book_repo.create_manual(
            title=title,
            authors=authors,
            description=description,
            page_count=page_count,
            cover_url=cover_url,
        )
        created = await self.suggestion_repo.add(cycle.id, book.id, user.id)
        if created is None:
            return book, False
        return book, True
