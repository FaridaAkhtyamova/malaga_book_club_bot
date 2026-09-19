from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SuggestionCycle


class CycleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, cycle_id: int) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle).where(SuggestionCycle.id == cycle_id)
        )
        return result.scalar_one_or_none()

    async def get_by_month(
        self, club_id: int, year: int, month: int
    ) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle).where(
                SuggestionCycle.club_id == club_id,
                SuggestionCycle.target_year == year,
                SuggestionCycle.target_month == month,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_suggesting(self, club_id: int) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle)
            .where(
                SuggestionCycle.club_id == club_id,
                SuggestionCycle.status == SuggestionCycle.STATUS_SUGGESTING,
            )
            .order_by(SuggestionCycle.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest(self, club_id: int) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle)
            .where(SuggestionCycle.club_id == club_id)
            .order_by(SuggestionCycle.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, club_id: int, year: int, month: int) -> SuggestionCycle:
        cycle = SuggestionCycle(
            club_id=club_id,
            target_year=year,
            target_month=month,
            status=SuggestionCycle.STATUS_SUGGESTING,
        )
        self.session.add(cycle)
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle

    async def set_status(self, cycle: SuggestionCycle, status: str) -> SuggestionCycle:
        cycle.status = status
        await self.session.commit()
        await self.session.refresh(cycle)
        return cycle
