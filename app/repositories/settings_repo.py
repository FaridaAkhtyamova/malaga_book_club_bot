from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import ClubSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self) -> ClubSettings:
        result = await self.session.execute(select(ClubSettings).limit(1))
        settings = result.scalar_one_or_none()
        env_group_id = get_settings().GROUP_CHAT_ID

        if settings is not None:
            if settings.group_chat_id is None and env_group_id is not None:
                settings.group_chat_id = env_group_id
                await self.session.commit()
                await self.session.refresh(settings)
            return settings

        settings = ClubSettings(group_chat_id=env_group_id, announce_hour=10)
        self.session.add(settings)
        await self.session.commit()
        await self.session.refresh(settings)
        return settings

    async def save(self, settings: ClubSettings) -> ClubSettings:
        await self.session.commit()
        await self.session.refresh(settings)
        return settings
