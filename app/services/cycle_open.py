from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Suggestion, SuggestionCycle
from app.repositories.cycle_repo import CycleRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.vote_poll_repo import VotePollRepository
from app.services.cycle_service import (
    CycleAlreadyOpenError,
    GroupNotSetError,
    announcement_text,
    next_year_month,
)


class CycleOpenService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings_repo = SettingsRepository(session)
        self.cycle_repo = CycleRepository(session)

    async def open_or_reopen(
        self,
        now: datetime | None = None,
    ) -> tuple[SuggestionCycle, str, bool]:
        settings = await self.settings_repo.get_or_create()
        if settings.group_chat_id is None:
            raise GroupNotSetError("Сначала привяжите группу командой /set_group.")

        tz = ZoneInfo(get_settings().TIMEZONE)
        current = datetime.now(tz) if now is None else now
        current = current.replace(tzinfo=tz) if current.tzinfo is None else current.astimezone(tz)

        year, month = next_year_month(current)
        existing = await self.cycle_repo.get_by_month(year, month)
        if existing is None:
            cycle = await self.cycle_repo.create(year, month)
            return cycle, announcement_text(month), True

        if existing.status == SuggestionCycle.STATUS_SUGGESTING:
            return existing, announcement_text(month), False

        if not get_settings().DEBUG:
            raise CycleAlreadyOpenError("Сбор предложений на этот месяц уже был открыт.")

        await VotePollRepository(self.session).delete_for_cycle(existing.id)
        existing.winner_book_id = None
        await self.session.execute(delete(Suggestion).where(Suggestion.cycle_id == existing.id))
        await self.session.commit()
        cycle = await self.cycle_repo.set_status(existing, SuggestionCycle.STATUS_SUGGESTING)
        return cycle, announcement_text(month), True
