from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SuggestionCycle


class CycleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_month(self, year: int, month: int) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle).where(
                SuggestionCycle.target_year == year,
                SuggestionCycle.target_month == month,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_suggesting(self) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle)
            .where(SuggestionCycle.status == SuggestionCycle.STATUS_SUGGESTING)
            .order_by(SuggestionCycle.opened_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest(self) -> SuggestionCycle | None:
        result = await self.session.execute(
            select(SuggestionCycle).order_by(SuggestionCycle.opened_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, year: int, month: int) -> SuggestionCycle:
        cycle = SuggestionCycle(
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
