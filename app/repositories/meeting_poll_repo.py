from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MeetingPoll


class MeetingPollRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        cycle_id: int,
        chat_id: int,
        message_id: int,
        telegram_poll_id: str | None,
        option_dates: Sequence[str | None],
    ) -> MeetingPoll:
        poll = MeetingPoll(
            cycle_id=cycle_id,
            chat_id=chat_id,
            message_id=message_id,
            telegram_poll_id=telegram_poll_id,
            option_dates=list(option_dates),
            is_open=True,
        )
        self.session.add(poll)
        await self.session.commit()
        await self.session.refresh(poll)
        return poll

    async def list_open(self, cycle_id: int) -> list[MeetingPoll]:
        result = await self.session.execute(
            select(MeetingPoll)
            .where(MeetingPoll.cycle_id == cycle_id, MeetingPoll.is_open.is_(True))
            .order_by(MeetingPoll.id.asc())
        )
        return list(result.scalars().all())

    async def mark_closed(self, poll: MeetingPoll) -> MeetingPoll:
        poll.is_open = False
        await self.session.commit()
        await self.session.refresh(poll)
        return poll
