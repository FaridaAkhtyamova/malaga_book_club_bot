from contextlib import suppress
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ChatMemberRestricted

from app.db.models import ClubSettings
from app.services.book_card import PHOTO_CAPTION_LIMIT
from app.services.cycle_service import CycleService


@dataclass(frozen=True, slots=True)
class SuggestAccess:
    allowed: bool
    error: str | None = None
    callback_error: str | None = None
    clear_state: bool = True


def forum_topic_url(chat_id: int, thread_id: int) -> str | None:
    chat = str(chat_id)
    if not chat.startswith("-100"):
        return None
    return f"https://t.me/c/{chat.removeprefix('-100')}/{thread_id}"


def wrong_topic_text(settings: ClubSettings) -> str:
    lines = [
        "📖 В группе предлагать книги нужно в топике клуба: карточка с #выбор_книги.",
        "Поиск по каталогу — в личке: /suggest",
    ]
    if settings.group_chat_id is not None and settings.suggest_topic_id is not None:
        url = forum_topic_url(settings.group_chat_id, settings.suggest_topic_id)
        if url is not None:
            lines.append(url)
    return "\n".join(lines)


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member.status in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}


async def club_admin_user_ids(bot: Bot, chat_id: int) -> list[int]:
    try:
        members = await bot.get_chat_administrators(chat_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return []
    return [member.user.id for member in members if not member.user.is_bot]


async def is_club_admin(
    bot: Bot,
    service: CycleService,
    user_id: int,
    *,
    current_chat_id: int | None,
    current_chat_type: ChatType | str | None,
) -> bool:
    settings = await service.get_settings()
    if settings.group_chat_id is not None:
        return await is_chat_admin(bot, settings.group_chat_id, user_id)
    if current_chat_id is None or current_chat_type is None:
        return False
    chat = ChatType(str(current_chat_type))
    if chat not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return False
    return await is_chat_admin(bot, current_chat_id, user_id)


async def is_club_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False

    if member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    }:
        return True
    if member.status == ChatMemberStatus.RESTRICTED and isinstance(member, ChatMemberRestricted):
        return member.is_member
    return False


async def resolve_suggest_access(
    bot: Bot,
    service: CycleService,
    *,
    chat_type: ChatType | str,
    chat_id: int,
    user_id: int,
    thread_id: int | None,
) -> SuggestAccess:
    settings = await service.get_settings()
    chat = ChatType(str(chat_type))

    if settings.group_chat_id is None:
        if chat in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return SuggestAccess(
                False,
                "Эта группа ещё не привязана. Админ: /set_group",
                "Группа клуба ещё не привязана.",
            )
        return SuggestAccess(False, "Группа клуба ещё не привязана.")

    if chat == ChatType.PRIVATE:
        if not await is_club_member(bot, settings.group_chat_id, user_id):
            text = "Предлагать книги могут только участники группы клуба."
            return SuggestAccess(False, text)
    elif chat in {ChatType.GROUP, ChatType.SUPERGROUP}:
        if settings.group_chat_id != chat_id:
            text = "Предлагать книги можно в группе клуба или в личке с ботом."
            return SuggestAccess(False, text)
        if not _topic_matches(settings.suggest_topic_id, thread_id):
            return SuggestAccess(
                False,
                wrong_topic_text(settings),
                "Предлагайте в топике поиска или в личке с ботом.",
                clear_state=False,
            )
    else:
        text = "Предлагать книги можно в группе клуба или в личке с ботом."
        return SuggestAccess(False, text)

    if await service.get_active_suggesting_cycle() is None:
        return SuggestAccess(False, "Предложения ещё не открыты.")
    return SuggestAccess(True)


def _topic_matches(expected: int | None, actual: int | None) -> bool:
    if expected is None:
        return True
    if expected == actual:
        return True
    # General forum topic is id 1; some clients send it as missing thread_id.
    return expected in {1, None} and actual in {1, None}


async def send_html_card(
    bot: Bot,
    chat_id: int,
    caption: str,
    cover_url: str | None,
    message_thread_id: int | None = None,
    *,
    parse_mode: ParseMode | None = ParseMode.HTML,
) -> None:
    if cover_url and len(caption) <= PHOTO_CAPTION_LIMIT:
        with suppress(TelegramBadRequest):
            await bot.send_photo(
                chat_id,
                photo=cover_url,
                caption=caption,
                parse_mode=parse_mode,
                message_thread_id=message_thread_id,
            )
            return
        with suppress(TelegramBadRequest):
            await bot.send_document(
                chat_id,
                document=cover_url,
                caption=caption,
                parse_mode=parse_mode,
                message_thread_id=message_thread_id,
            )
            return
    elif cover_url:
        sent_cover = False
        with suppress(TelegramBadRequest):
            await bot.send_photo(
                chat_id,
                photo=cover_url,
                message_thread_id=message_thread_id,
            )
            sent_cover = True
        if not sent_cover:
            with suppress(TelegramBadRequest):
                await bot.send_document(
                    chat_id,
                    document=cover_url,
                    message_thread_id=message_thread_id,
                )

    await bot.send_message(
        chat_id,
        caption,
        parse_mode=parse_mode,
        message_thread_id=message_thread_id,
    )
