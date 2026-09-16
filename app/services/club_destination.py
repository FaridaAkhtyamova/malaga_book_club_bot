from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClubSettings
from app.repositories.settings_repo import SettingsRepository
from app.services.cycle_service import GroupNotSetError, month_name_ru


@dataclass(frozen=True, slots=True)
class ClubDestination:
    chat_id: int
    message_thread_id: int | None = None


class DestinationService:
    def __init__(self, session: AsyncSession) -> None:
        self.settings_repo = SettingsRepository(session)

    async def bind_suggest_topic(self, chat_id: int, thread_id: int) -> ClubSettings:
        settings = await self.settings_repo.get_or_create()
        if settings.group_chat_id is None:
            raise GroupNotSetError("Сначала привяжите группу командой /set_group.")
        if settings.group_chat_id != chat_id:
            raise GroupNotSetError("Сначала привяжите эту группу командой /set_group.")
        settings.suggest_topic_id = thread_id
        return await self.settings_repo.save(settings)

    async def clear_suggest_topic(self) -> ClubSettings:
        settings = await self.settings_repo.get_or_create()
        settings.suggest_topic_id = None
        return await self.settings_repo.save(settings)

    async def clear_topic_if_group_changed(
        self,
        previous_group_id: int | None,
        chat_id: int,
    ) -> None:
        if previous_group_id == chat_id:
            return
        await self.clear_suggest_topic()

    async def get_destination(self) -> ClubDestination | None:
        settings = await self.settings_repo.get_or_create()
        if settings.group_chat_id is None:
            return None
        return ClubDestination(
            chat_id=settings.group_chat_id,
            message_thread_id=settings.suggest_topic_id,
        )


def suggestion_announcement_text(month: int) -> str:
    return (
        f"📚 Дорогой клуб, начинаем предлагать книги на {month_name_ru(month)}.\n\n"
        "В группе запостите карточку:\n"
        "#выбор_книги Название книги, 500\n"
        "Краткое описание книги\n\n"
        "Поиск по каталогу — в личке с ботом, кнопка ниже."
    )
