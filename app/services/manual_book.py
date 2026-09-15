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
    ) -> tuple[Book, bool]:
        cycle = await self.cycle_repo.get_latest_suggesting()
        if cycle is None:
            raise CycleNotOpenError("Предложения ещё не открыты.")

        needle = title.casefold()
        for existing in await self.suggestion_repo.list_books(cycle.id):
            if existing.title.casefold() == needle:
                return existing, False

        book = await self.book_repo.create_manual(
            title=title,
            authors=authors,
            description=description,
            page_count=page_count,
        )
        created = await self.suggestion_repo.add(cycle.id, book.id, user.id)
        if created is None:
            return book, False
        return book, True
