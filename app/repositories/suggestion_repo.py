from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Book, Suggestion, SuggestionCycle


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

    async def add(
        self,
        cycle_id: int,
        book_id: int,
        user_id: int,
        *,
        source_chat_id: int | None = None,
        source_message_id: int | None = None,
    ) -> Suggestion | None:
        suggestion = Suggestion(
            cycle_id=cycle_id,
            book_id=book_id,
            user_id=user_id,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
        )
        self.session.add(suggestion)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        await self.session.refresh(suggestion)
        return suggestion

    async def set_source_message(
        self,
        cycle_id: int,
        book_id: int,
        chat_id: int,
        message_id: int,
    ) -> bool:
        result = await self.session.execute(
            update(Suggestion)
            .where(Suggestion.cycle_id == cycle_id, Suggestion.book_id == book_id)
            .values(source_chat_id=chat_id, source_message_id=message_id)
            .returning(Suggestion.id)
        )
        updated = result.scalar_one_or_none() is not None
        if updated:
            await self.session.commit()
        return updated

    async def count(self, cycle_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Suggestion).where(Suggestion.cycle_id == cycle_id)
        )
        return int(result.scalar_one())

    async def list_user_ids_for_club(self, club_id: int) -> list[int]:
        result = await self.session.execute(
            select(Suggestion.user_id)
            .join(SuggestionCycle, SuggestionCycle.id == Suggestion.cycle_id)
            .where(SuggestionCycle.club_id == club_id)
            .distinct()
        )
        return list(result.scalars().all())

    async def list_books(self, cycle_id: int) -> list[Book]:
        result = await self.session.execute(
            select(Suggestion)
            .where(Suggestion.cycle_id == cycle_id)
            .options(selectinload(Suggestion.book))
            .order_by(Suggestion.created_at.asc())
        )
        suggestions = result.scalars().all()
        return [suggestion.book for suggestion in suggestions]

    async def list_suggestions(self, cycle_id: int) -> list[Suggestion]:
        result = await self.session.execute(
            select(Suggestion)
            .where(Suggestion.cycle_id == cycle_id)
            .options(selectinload(Suggestion.book))
            .order_by(Suggestion.id.asc())
        )
        return list(result.scalars().all())

    async def remove(self, cycle_id: int, book_id: int) -> bool:
        result = await self.session.execute(
            delete(Suggestion).where(
                Suggestion.cycle_id == cycle_id,
                Suggestion.book_id == book_id,
            ).returning(Suggestion.id)
        )
        removed = result.scalar_one_or_none() is not None
        await self.session.commit()
        return removed
