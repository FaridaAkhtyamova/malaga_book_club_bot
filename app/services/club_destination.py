from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClubSettings
from app.repositories.settings_repo import SettingsRepository
from app.services.cycle_service import GroupNotSetError, month_name_ru
from app.services.hashtag_suggest import CARD_TEMPLATE


@dataclass(frozen=True, slots=True)
class ClubDestination:
    chat_id: int
    message_thread_id: int | None = None


def club_label(club: ClubSettings, *, limit: int | None = None) -> str:
    if club.title and club.title.strip():
        raw = club.title.strip()
    elif club.group_chat_id is not None:
        raw = f"группа {club.group_chat_id}"
    else:
        raw = f"клуб {club.id}"
    if limit is None or len(raw) <= limit:
        return raw
    if limit <= 1:
        return raw[:limit]
    return raw[: limit - 1] + "…"


def destination_of(club: ClubSettings) -> ClubDestination | None:
    if club.group_chat_id is None:
        return None
    return ClubDestination(
        chat_id=club.group_chat_id,
        message_thread_id=club.suggest_topic_id,
    )


def select_club(
    clubs: list[ClubSettings],
    *,
    active_id: int | None,
    prefer_ids: list[int] | None = None,
) -> ClubSettings | None:
    by_id = {club.id: club for club in clubs}
    if active_id is not None and active_id in by_id:
        return by_id[active_id]
    if len(clubs) == 1:
        return clubs[0]
    if prefer_ids is not None:
        preferred = [club for club in clubs if club.id in prefer_ids]
        if len(preferred) == 1:
            return preferred[0]
    return None


class DestinationService:
    def __init__(self, session: AsyncSession, club: ClubSettings) -> None:
        self.settings_repo = SettingsRepository(session)
        self.club = club

    async def bind_suggest_topic(self, chat_id: int, thread_id: int) -> ClubSettings:
        if self.club.group_chat_id is None:
            raise GroupNotSetError("Сначала привяжите группу командой /set_group.")
        if self.club.group_chat_id != chat_id:
            raise GroupNotSetError("Сначала привяжите эту группу командой /set_group.")
        self.club.suggest_topic_id = thread_id
        return await self.settings_repo.save(self.club)

    async def clear_suggest_topic(self) -> ClubSettings:
        self.club.suggest_topic_id = None
        return await self.settings_repo.save(self.club)

    def get_destination(self) -> ClubDestination | None:
        return destination_of(self.club)


def suggestion_announcement_text(month: int) -> str:
    return (
        f"📚 Дорогой клуб, начинаем предлагать книги на {month_name_ru(month)}.\n\n"
        "В группе запостите карточку. После тега — название, затем автор. "
        "Число страниц бот найдёт в любой строке со словами «стр» / «страниц». "
        "Кто предложил — из вашего сообщения. Перед голосованием карточку проверит админ.\n"
        f"{CARD_TEMPLATE}\n\n"
        "Обложку можно прикрепить картинкой.\n"
        "Поиск по каталогу — в личке с ботом, кнопка ниже."
    )
