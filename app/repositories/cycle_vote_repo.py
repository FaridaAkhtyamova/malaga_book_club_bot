from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import SuggestionCycle


class CycleVoteRepository:
    """Queries for voting status and the chosen book of a cycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_voting(self, club_id: int) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle)
            .where(
                SuggestionCycle.club_id == club_id,
                SuggestionCycle.status == SuggestionCycle.STATUS_VOTING,
            )
            .order_by(SuggestionCycle.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_with_winner(self, club_id: int) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle)
            .where(
                SuggestionCycle.club_id == club_id,
                SuggestionCycle.winner_book_id.is_not(None),
            )
            .options(selectinload(SuggestionCycle.winner))
            .order_by(SuggestionCycle.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def set_winner(self, cycle: SuggestionCycle, book_id: int) -> SuggestionCycle:
        cycle.winner_book_id = book_id
        cycle.status = SuggestionCycle.STATUS_CLOSED
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle

    async def set_meeting_date(self, cycle: SuggestionCycle, meeting_day: date) -> SuggestionCycle:
        cycle.winner_meeting_date = meeting_day
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle

    async def clear_meeting_date(self, cycle: SuggestionCycle) -> SuggestionCycle:
        cycle.winner_meeting_date = None
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle

    async def set_meeting_hour(self, cycle: SuggestionCycle, hour: int) -> SuggestionCycle:
        cycle.winner_meeting_hour = hour
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle

    async def clear_meeting_hour(self, cycle: SuggestionCycle) -> SuggestionCycle:
        cycle.winner_meeting_hour = None
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle

    async def clear_winner(self, cycle: SuggestionCycle) -> SuggestionCycle:
        cycle.winner_book_id = None
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle
