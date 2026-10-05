from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VotePoll


class VotePollRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stage_many(self, polls: Sequence[VotePoll]) -> None:
        self.session.add_all(polls)

    async def list_open(self, cycle_id: int) -> list[VotePoll]:
        result = await self.session.execute(
            select(VotePoll)
            .where(VotePoll.cycle_id == cycle_id, VotePoll.is_open.is_(True))
            .order_by(VotePoll.id.asc())
        )
        return list(result.scalars().all())

    async def mark_closed(self, poll: VotePoll) -> VotePoll:
        poll.is_open = False
        await self.session.commit()
        await self.session.refresh(poll)
        return poll

    async def delete_for_cycle(self, cycle_id: int) -> None:
        polls = await self.session.execute(select(VotePoll).where(VotePoll.cycle_id == cycle_id))
        for poll in polls.scalars().all():
            await self.session.delete(poll)
        await self.session.commit()
