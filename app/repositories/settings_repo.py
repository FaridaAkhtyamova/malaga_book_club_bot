from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import ClubSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, club_id: int) -> ClubSettings | None:
        result = await self.session.execute(
            select(ClubSettings).where(ClubSettings.id == club_id)
        )
        return result.scalar_one_or_none()

    async def get_by_chat_id(self, chat_id: int) -> ClubSettings | None:
        result = await self.session.execute(
            select(ClubSettings).where(ClubSettings.group_chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def list_bound(self) -> list[ClubSettings]:
        result = await self.session.execute(
            select(ClubSettings)
            .where(ClubSettings.group_chat_id.is_not(None))
            .order_by(ClubSettings.id)
        )
        return list(result.scalars().all())

    async def bind_group(self, chat_id: int, title: str | None) -> ClubSettings:
        club = await self.get_by_chat_id(chat_id)
        clipped = title[:255] if title else None
        if club is not None:
            if clipped:
                club.title = clipped
            return await self.save(club)

        unbound = await self.session.execute(
            select(ClubSettings)
            .where(ClubSettings.group_chat_id.is_(None))
            .order_by(ClubSettings.id)
            .limit(1)
        )
        leftover = unbound.scalar_one_or_none()
        if leftover is not None:
            leftover.group_chat_id = chat_id
            if clipped:
                leftover.title = clipped
            return await self.save(leftover)

        club = ClubSettings(group_chat_id=chat_id, title=clipped, announce_hour=10)
        self.session.add(club)
        await self.session.commit()
        await self.session.refresh(club)
        return club

    async def ensure_env_group(self) -> ClubSettings | None:
        env_group_id = get_settings().GROUP_CHAT_ID
        if env_group_id is None:
            return None
        return await self.bind_group(env_group_id, title=None)

    async def save(self, settings: ClubSettings) -> ClubSettings:
        await self.session.commit()
        await self.session.refresh(settings)
        return settings
