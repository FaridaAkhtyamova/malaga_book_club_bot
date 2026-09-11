import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.handlers.base import router as base_router
from app.bot.middlewares.db import DbSessionMiddleware
from app.core.config import get_settings


settings = get_settings()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    dp.message.middleware(DbSessionMiddleware())
    dp.include_router(base_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
