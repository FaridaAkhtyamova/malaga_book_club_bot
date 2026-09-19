from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.club import ClubPickCallback
from app.bot.club_chat import clubs_where_admin, clubs_where_member
from app.bot.club_context import (
    chosen_club_text,
    format_clubs_list,
    load_picked_club,
)
from app.bot.handlers.books import begin_suggest
from app.bot.keyboards.club import club_pick_keyboard
from app.repositories.user_repo import UserRepository

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)


@router.message(Command("clubs"))
async def cmd_clubs(message: Message, session: AsyncSession, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return
    clubs = await clubs_where_member(bot, session, user.id)
    if not clubs:
        admin_clubs = await clubs_where_admin(bot, session, user.id)
        clubs = admin_clubs
    stored = await UserRepository(session).get_by_id(user.id)
    active_id = None if stored is None else stored.active_club_id
    markup = club_pick_keyboard(clubs, action="active") if len(clubs) > 1 else None
    await message.answer(format_clubs_list(clubs, active_id=active_id), reply_markup=markup)


@router.callback_query(ClubPickCallback.filter())
async def on_club_picked(
    callback: CallbackQuery,
    callback_data: ClubPickCallback,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    club = await load_picked_club(
        callback,
        session,
        callback_data.club_id,
        bot=bot,
    )
    if club is None:
        return

    message = callback.message if isinstance(callback.message, Message) else None
    await callback.answer()
    if callback_data.action == "suggest":
        if message is None or callback.from_user is None:
            return
        data = await state.get_data()
        query_raw = data.get("pending_suggest_query")
        query = query_raw.strip() if isinstance(query_raw, str) and query_raw.strip() else None
        await state.update_data(pending_suggest_query=None)
        await begin_suggest(
            message, state, session, bot, query=query, actor=callback.from_user
        )
        return

    text = chosen_club_text(club, retry=True)
    if message is not None:
        await message.answer(text)
        return
    if callback.from_user is not None:
        await bot.send_message(callback.from_user.id, text)
