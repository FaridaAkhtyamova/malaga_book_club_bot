from collections.abc import Sequence

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_chat import clubs_where_admin, clubs_where_member
from app.bot.keyboards.club import club_pick_keyboard
from app.db.models import ClubSettings, User
from app.repositories.settings_repo import SettingsRepository
from app.repositories.user_repo import UserRepository
from app.services.club_destination import club_label, select_club

_PICK_ADMIN = "Вы в нескольких группах. Выберите, с какой работать в личке, и повторите команду."
_PICK_SUGGEST = "Вы в нескольких группах. Выберите, с какой работать в личке."
_NO_MEMBER_CLUB = "Предлагать книги могут только участники группы клуба."
_NO_ADMIN_CLUB = "Сначала привяжите группу командой /set_group."
_CLUB_CHOSEN = "Группа: {name}."
_CLUB_CHOSEN_RETRY = "Группа: {name}. Повторите команду."


async def require_admin_club(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    *,
    user_id: int | None = None,
) -> ClubSettings | None:
    actor_id = user_id if user_id is not None else (
        None if message.from_user is None else message.from_user.id
    )
    if actor_id is None:
        return None
    clubs = await clubs_where_admin(bot, session, actor_id)
    if not clubs:
        await message.answer(_NO_ADMIN_CLUB)
        return None
    chosen = await _resolve_club(session, actor_id, clubs)
    if chosen is not None:
        return chosen
    await message.answer(_PICK_ADMIN, reply_markup=club_pick_keyboard(clubs, action="active"))
    return None


async def require_member_club(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    *,
    user_id: int | None = None,
    pick_action: str = "suggest",
) -> ClubSettings | None:
    actor_id = user_id if user_id is not None else (
        None if message.from_user is None else message.from_user.id
    )
    if actor_id is None:
        return None
    clubs = await clubs_where_member(bot, session, actor_id)
    if not clubs:
        await message.answer(_NO_MEMBER_CLUB)
        return None
    chosen = await _resolve_club(session, actor_id, clubs)
    if chosen is not None:
        return chosen
    await message.answer(
        _PICK_SUGGEST,
        reply_markup=club_pick_keyboard(clubs, action=pick_action),
    )
    return None


async def club_from_state(
    state: FSMContext,
    session: AsyncSession,
) -> ClubSettings | None:
    data = await state.get_data()
    raw = data.get("club_id")
    if not isinstance(raw, int):
        return None
    return await SettingsRepository(session).get(raw)


async def remember_club(state: FSMContext, club: ClubSettings) -> None:
    await state.update_data(club_id=club.id)


async def set_active_club(
    session: AsyncSession,
    telegram_id: int,
    club: ClubSettings,
    *,
    username: str | None,
    full_name: str | None,
) -> User:
    repo = UserRepository(session)
    user = await repo.get_or_create_user(telegram_id, username, full_name)
    return await repo.set_active_club(user, club.id)


def chosen_club_text(club: ClubSettings, *, retry: bool = False) -> str:
    template = _CLUB_CHOSEN_RETRY if retry else _CLUB_CHOSEN
    return template.format(name=club_label(club))


async def load_picked_club(
    callback: CallbackQuery,
    session: AsyncSession,
    club_id: int,
    bot: Bot,
) -> ClubSettings | None:
    user = callback.from_user
    if user is None:
        await callback.answer()
        return None
    clubs = {
        club.id: club
        for club in await clubs_where_member(bot, session, user.id)
    }
    for club in await clubs_where_admin(bot, session, user.id):
        clubs[club.id] = club
    picked = clubs.get(club_id)
    if picked is None:
        await callback.answer("Эта группа больше недоступна.", show_alert=True)
        return None
    await set_active_club(
        session,
        user.id,
        picked,
        username=user.username,
        full_name=user.full_name,
    )
    return picked


def format_clubs_list(
    clubs: Sequence[ClubSettings],
    *,
    active_id: int | None,
) -> str:
    if not clubs:
        return "Нет группы, с которой можно работать в личке."
    if len(clubs) == 1:
        return f"В личке используется группа {club_label(clubs[0])}."
    lines = ["Выберите, с какой группой работать в личке:"]
    for club in clubs:
        mark = " ✓" if club.id == active_id else ""
        lines.append(f"• {club_label(club)}{mark}")
    return "\n".join(lines)


async def _resolve_club(
    session: AsyncSession,
    user_id: int,
    clubs: list[ClubSettings],
) -> ClubSettings | None:
    user = await UserRepository(session).get_by_id(user_id)
    active_id = None if user is None else user.active_club_id
    chosen = select_club(clubs, active_id=active_id)
    if chosen is None:
        return None
    if user is None or user.active_club_id != chosen.id:
        if user is None:
            user = await UserRepository(session).get_or_create_user(user_id, None, None)
        await UserRepository(session).set_active_club(user, chosen.id)
    return chosen
