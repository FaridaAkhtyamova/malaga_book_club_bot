import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.commands import setup_bot_commands
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.base import router as base_router
from app.bot.handlers.books import router as books_router
from app.bot.handlers.club_setup import router as club_setup_router
from app.bot.handlers.cycle_open import router as cycle_open_router
from app.bot.handlers.group_card_review import router as group_card_review_router
from app.bot.handlers.group_suggest import router as group_suggest_router
from app.bot.handlers.meeting import router as meeting_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.core.config import get_settings
from app.services.club_scheduler import create_scheduler

settings = get_settings()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    bot = Bot(token=settings.BOT_TOKEN)
    if settings.DEBUG:
        logging.warning("DEBUG mode is on: /open_suggestions can reset the current month")
    await setup_bot_commands(bot)
    dp = Dispatcher(storage=MemoryStorage())

    db_middleware = DbSessionMiddleware()
    dp.message.middleware(db_middleware)
    dp.edited_message.middleware(db_middleware)
    dp.callback_query.middleware(db_middleware)
    dp.include_router(cycle_open_router)
    dp.include_router(club_setup_router)
    dp.include_router(meeting_router)
    dp.include_router(admin_router)
    dp.include_router(group_card_review_router)
    dp.include_router(group_suggest_router)
    dp.include_router(base_router)
    dp.include_router(books_router)

    scheduler = create_scheduler(bot)
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
