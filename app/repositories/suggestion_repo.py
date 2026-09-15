from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Book, Suggestion


class SuggestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, cycle_id: int, book_id: int) -> bool:
        result = await self.session.execute(
            select(Suggestion.id).where(
                Suggestion.cycle_id == cycle_id,
                Suggestion.book_id == book_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def add(self, cycle_id: int, book_id: int, user_id: int) -> Suggestion | None:
        suggestion = Suggestion(cycle_id=cycle_id, book_id=book_id, user_id=user_id)
        self.session.add(suggestion)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        await self.session.refresh(suggestion)
        return suggestion

    async def count(self, cycle_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Suggestion).where(Suggestion.cycle_id == cycle_id)
        )
        return int(result.scalar_one())

    async def list_books(self, cycle_id: int) -> list[Book]:
        result = await self.session.execute(
            select(Suggestion)
            .where(Suggestion.cycle_id == cycle_id)
            .options(selectinload(Suggestion.book))
            .order_by(Suggestion.created_at.asc())
        )
        suggestions = result.scalars().all()
        return [suggestion.book for suggestion in suggestions]
