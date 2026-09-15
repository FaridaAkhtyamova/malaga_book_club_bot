import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.club_publish import publish_club_announcement, publish_vote_polls
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.services.club_destination import DestinationService, suggestion_announcement_text
from app.services.cycle_service import (
    MONTH_NAMES_RU,
    CycleService,
    ScheduledAnnounce,
    ScheduledVote,
)

logger = logging.getLogger(__name__)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    timezone = ZoneInfo(get_settings().TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        run_scheduled_jobs,
        "cron",
        minute=0,
        args=[bot],
        id="club_cycle_hourly",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


async def run_scheduled_jobs(bot: Bot) -> None:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.TIMEZONE))
    async with AsyncSessionLocal() as session:
        service = CycleService(session)
        action = await service.run_scheduled(now)
        if action is None:
            return

        dest = await DestinationService(session).get_destination()
        if dest is None:
            return

        try:
            if isinstance(action, ScheduledAnnounce):
                text = _announcement_from_scheduled(action.text)
                await publish_club_announcement(bot, dest, text)
            elif isinstance(action, ScheduledVote):
                await publish_vote_polls(bot, dest, action.cycle, action.chunks)
        except Exception:
            logger.exception("Failed to publish scheduled club message")


def _announcement_from_scheduled(text: str) -> str:
    if "личке" in text:
        return text
    month = _month_from_announce(text)
    if month is None:
        return (
            f"{text}\n\n"
            "Предложить книгу можно командой /suggest здесь "
            "или в личке с ботом — кнопка ниже."
        )
    return suggestion_announcement_text(month)


def _month_from_announce(text: str) -> int | None:
    lowered = text.casefold()
    for month, name in MONTH_NAMES_RU.items():
        if name in lowered:
            return month
    return None
