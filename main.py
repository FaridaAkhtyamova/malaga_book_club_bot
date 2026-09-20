import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.commands import setup_bot_commands
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.base import router as base_router
from app.bot.handlers.books import router as books_router
from app.bot.handlers.club_setup import router as club_setup_router
from app.bot.handlers.clubs import router as clubs_router
from app.bot.handlers.cycle_open import router as cycle_open_router
from app.bot.handlers.group_card_review import router as group_card_review_router
from app.bot.handlers.group_suggest import router as group_suggest_router
from app.bot.handlers.meeting import router as meeting_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.telegram_session import CalendarFileSession
from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.http.calendar import start_calendar_http, stop_calendar_http
from app.repositories.settings_repo import SettingsRepository
from app.services.club_scheduler import create_scheduler

settings = get_settings()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    bot = Bot(token=settings.BOT_TOKEN, session=CalendarFileSession())
    if settings.DEBUG:
        logging.warning("DEBUG mode is on: /open_suggestions can reset the current month")
    async with AsyncSessionLocal() as session:
        repo = SettingsRepository(session)
        await repo.ensure_env_group()
        clubs = await repo.list_bound()
        await setup_bot_commands(
            bot,
            [club.group_chat_id for club in clubs if club.group_chat_id is not None],
        )
    dp = Dispatcher(storage=MemoryStorage())

    # Outer middleware so session is available to router-level filters (e.g. AdminFilter).
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.include_router(cycle_open_router)
    dp.include_router(club_setup_router)
    dp.include_router(meeting_router)
    dp.include_router(admin_router)
    dp.include_router(group_card_review_router)
    dp.include_router(group_suggest_router)
    dp.include_router(clubs_router)
    dp.include_router(base_router)
    dp.include_router(books_router)

    scheduler = create_scheduler(bot)
    scheduler.start()
    calendar_http = await start_calendar_http()
    try:
        await dp.start_polling(bot)
    finally:
        await stop_calendar_http(calendar_http)
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
