from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.deep_linking import create_start_link
from aiogram.utils.keyboard import InlineKeyboardBuilder

SUGGEST_START_PAYLOAD = "suggest"


async def suggest_dm_keyboard(bot: Bot) -> InlineKeyboardMarkup:
    url = await create_start_link(bot, SUGGEST_START_PAYLOAD)
    builder = InlineKeyboardBuilder()
    builder.button(text="Предложить в личке", url=url)
    return builder.as_markup()
