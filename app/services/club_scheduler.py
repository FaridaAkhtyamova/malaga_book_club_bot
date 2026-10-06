import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.club_publish import (
    check_vote_book_sources,
    notify_vote_source_review,
    publish_club_announcement,
    publish_vote_polls,
    record_vote_polls_or_stop,
    send_pending_card_reviews,
)
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.repositories.settings_repo import SettingsRepository
from app.services.club_destination import destination_of, suggestion_announcement_text
from app.services.cycle_service import (
    MONTH_NAMES_RU,
    CycleService,
    ScheduledAnnounce,
    ScheduledPendingReview,
    ScheduledSuggestionReminder,
    ScheduledVote,
)

logger = logging.getLogger(__name__)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    timezone = ZoneInfo(get_settings().TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        run_scheduled_jobs,
        "cron",
        hour=10,
        minute=0,
        args=[bot],
        id="club_cycle_daily",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


async def run_scheduled_jobs(bot: Bot) -> None:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.TIMEZONE))
    async with AsyncSessionLocal() as session:
        clubs = await SettingsRepository(session).list_bound()
        group_chat_ids = [club.group_chat_id for club in clubs if club.group_chat_id is not None]

    for chat_id in group_chat_ids:
        async with AsyncSessionLocal() as session:
            club = await SettingsRepository(session).get_by_chat_id(chat_id)
            if club is None:
                continue
            dest = destination_of(club)
            if dest is None:
                continue
            service = CycleService(session, club)
            try:
                action = await service.run_scheduled(now)
            except Exception:
                logger.exception("Failed scheduled cycle for club %s", club.id)
                await session.rollback()
                continue
            if action is None:
                continue
            try:
                if isinstance(action, ScheduledAnnounce):
                    text = _announcement_from_scheduled(action.text)
                    await publish_club_announcement(bot, dest, text)
                elif isinstance(action, ScheduledSuggestionReminder):
                    month = MONTH_NAMES_RU[action.cycle.target_month]
                    await publish_club_announcement(
                        bot,
                        dest,
                        f"Завтра последний день, когда можно предложить книгу на {month}.\n"
                        "Успейте добавить свою книгу сегодня!",
                    )
                elif isinstance(action, ScheduledPendingReview):
                    await send_pending_card_reviews(bot, action.cards, session)
                elif isinstance(action, ScheduledVote):
                    books = [book for chunk in action.chunks for book in chunk]
                    source_check = await check_vote_book_sources(
                        bot, service, action.cycle, books
                    )
                    review_text = await notify_vote_source_review(
                        bot,
                        dest.chat_id,
                        action.cycle.id,
                        source_check,
                    )
                    if review_text is None:
                        published = await publish_vote_polls(
                            bot, dest, action.cycle, source_check.chunks
                        )
                        await record_vote_polls_or_stop(
                            bot, service, action.cycle, published, mark_voting=True
                        )
            except Exception:
                logger.exception("Failed to publish scheduled club message for club %s", club.id)
                await session.rollback()


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
