from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PendingGroupCard


class PendingGroupCardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, card_id: int) -> PendingGroupCard | None:
        return await self.session.get(PendingGroupCard, card_id)

    async def get_by_message(
        self,
        cycle_id: int,
        chat_id: int,
        message_id: int,
    ) -> PendingGroupCard | None:
        result = await self.session.execute(
            select(PendingGroupCard).where(
                PendingGroupCard.cycle_id == cycle_id,
                PendingGroupCard.chat_id == chat_id,
                PendingGroupCard.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending(self, cycle_id: int) -> list[PendingGroupCard]:
        result = await self.session.execute(
            select(PendingGroupCard)
            .where(
                PendingGroupCard.cycle_id == cycle_id,
                PendingGroupCard.status == PendingGroupCard.STATUS_PENDING,
            )
            .order_by(PendingGroupCard.id.asc())
        )
        return list(result.scalars().all())

    async def count_pending(self, cycle_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(PendingGroupCard)
            .where(
                PendingGroupCard.cycle_id == cycle_id,
                PendingGroupCard.status == PendingGroupCard.STATUS_PENDING,
            )
        )
        return int(result.scalar_one())

    async def add(self, card: PendingGroupCard) -> PendingGroupCard:
        self.session.add(card)
        await self.session.commit()
        await self.session.refresh(card)
        return card

    async def save(self, card: PendingGroupCard) -> PendingGroupCard:
        await self.session.commit()
        await self.session.refresh(card)
        return card

    async def claim(
        self,
        card_id: int,
        status: str,
    ) -> PendingGroupCard | None:
        result = await self.session.execute(
            update(PendingGroupCard)
            .where(
                PendingGroupCard.id == card_id,
                PendingGroupCard.status == PendingGroupCard.STATUS_PENDING,
            )
            .values(status=status)
            .returning(PendingGroupCard.id)
        )
        claimed_id = result.scalar_one_or_none()
        if claimed_id is None:
            return None
        await self.session.commit()
        return await self.get(claimed_id)

    async def delete_for_cycle(self, cycle_id: int) -> None:
        await self.session.execute(
            delete(PendingGroupCard).where(PendingGroupCard.cycle_id == cycle_id)
        )
        await self.session.commit()
