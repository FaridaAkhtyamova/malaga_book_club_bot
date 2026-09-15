import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.polls import publish_vote_polls
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.services.cycle_service import CycleService, ScheduledAnnounce, ScheduledVote

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

        club = await service.get_settings()
        if club.group_chat_id is None:
            return

        try:
            if isinstance(action, ScheduledAnnounce):
                await bot.send_message(club.group_chat_id, action.text)
            elif isinstance(action, ScheduledVote):
                await publish_vote_polls(bot, club.group_chat_id, action.cycle, action.chunks)
        except Exception:
            logger.exception("Failed to publish scheduled club message")
