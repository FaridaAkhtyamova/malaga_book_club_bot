from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MeetingTimePoll


class MeetingTimePollRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        cycle_id: int,
        chat_id: int,
        message_id: int,
        telegram_poll_id: str | None,
        option_hours: Sequence[int],
    ) -> MeetingTimePoll:
        poll = MeetingTimePoll(
            cycle_id=cycle_id,
            chat_id=chat_id,
            message_id=message_id,
            telegram_poll_id=telegram_poll_id,
            option_hours=list(option_hours),
            is_open=True,
        )
        self.session.add(poll)
        await self.session.commit()
        await self.session.refresh(poll)
        return poll

    async def list_open(self, cycle_id: int) -> list[MeetingTimePoll]:
        result = await self.session.execute(
            select(MeetingTimePoll)
            .where(MeetingTimePoll.cycle_id == cycle_id, MeetingTimePoll.is_open.is_(True))
            .order_by(MeetingTimePoll.id.asc())
        )
        return list(result.scalars().all())

    async def mark_closed(self, poll: MeetingTimePoll) -> MeetingTimePoll:
        poll.is_open = False
        await self.session.commit()
        await self.session.refresh(poll)
        return poll
