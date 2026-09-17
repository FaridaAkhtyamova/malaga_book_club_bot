from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Book, Suggestion


class SuggestionPeriodRepository:
    """Suggestion queries scoped to a collection window."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_books_since(self, cycle_id: int, since: datetime) -> list[Book]:
        result = await self.session.execute(
            select(Suggestion)
            .where(
                Suggestion.cycle_id == cycle_id,
                Suggestion.created_at >= since,
            )
            .options(selectinload(Suggestion.book))
            .order_by(Suggestion.created_at.asc())
        )
        suggestions = result.scalars().all()
        return [suggestion.book for suggestion in suggestions]

    async def delete_before(self, cycle_id: int, before: datetime) -> int:
        result = await self.session.execute(
            delete(Suggestion).where(
                Suggestion.cycle_id == cycle_id,
                Suggestion.created_at < before,
            )
        )
        await self.session.commit()
        return int(result.rowcount or 0)
