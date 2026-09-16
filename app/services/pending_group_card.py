from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PendingGroupCard, User
from app.repositories.cycle_repo import CycleRepository
from app.repositories.pending_group_card_repo import PendingGroupCardRepository
from app.repositories.user_repo import UserRepository
from app.services.cycle_service import CycleNotOpenError
from app.services.hashtag_suggest import HashtagSuggestion
from app.services.manual_book import ManualBookService


class PendingCardNotFoundError(Exception):
    """The queued group card is missing or already reviewed."""


class PendingCardNeedsTitleError(Exception):
    """Approve is blocked until the admin types a title."""


class PendingGroupCardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cycle_repo = CycleRepository(session)
        self.card_repo = PendingGroupCardRepository(session)
        self.user_repo = UserRepository(session)

    async def get(self, card_id: int) -> PendingGroupCard | None:
        return await self.card_repo.get(card_id)

    async def list_pending(self, cycle_id: int) -> list[PendingGroupCard]:
        return await self.card_repo.list_pending(cycle_id)

    async def count_pending(self, cycle_id: int) -> int:
        return await self.card_repo.count_pending(cycle_id)

    async def upsert_from_post(
        self,
        user: User,
        *,
        chat_id: int,
        message_id: int,
        raw_text: str,
        parsed: HashtagSuggestion | None,
        cover_url: str | None = None,
    ) -> tuple[PendingGroupCard, bool]:
        cycle = await self.cycle_repo.get_latest_suggesting()
        if cycle is None:
            raise CycleNotOpenError("Предложения ещё не открыты.")

        existing = await self.card_repo.get_by_message(cycle.id, chat_id, message_id)
        title = parsed.title if parsed is not None else None
        authors = parsed.authors if parsed is not None else None
        description = parsed.description if parsed is not None else None
        page_count = parsed.page_count if parsed is not None else None
        if existing is None:
            card = await self.card_repo.add(
                PendingGroupCard(
                    cycle_id=cycle.id,
                    chat_id=chat_id,
                    message_id=message_id,
                    user_id=user.id,
                    raw_text=raw_text,
                    title=title,
                    authors=authors,
                    description=description,
                    page_count=page_count,
                    cover_url=cover_url,
                    status=PendingGroupCard.STATUS_PENDING,
                )
            )
            return card, True
        if existing.status != PendingGroupCard.STATUS_PENDING:
            return existing, False
        existing.user_id = user.id
        existing.raw_text = raw_text
        existing.title = title
        existing.authors = authors
        existing.description = description
        existing.page_count = page_count
        if cover_url:
            existing.cover_url = cover_url
        return await self.card_repo.save(existing), False

    async def get_pending(self, card_id: int) -> PendingGroupCard:
        card = await self.card_repo.get(card_id)
        if card is None or card.status != PendingGroupCard.STATUS_PENDING:
            raise PendingCardNotFoundError("Эта карточка уже разобрана или не найдена.")
        return card

    async def set_cover(self, card_id: int, cover_url: str) -> PendingGroupCard | None:
        card = await self.card_repo.get(card_id)
        if card is None or card.status != PendingGroupCard.STATUS_PENDING:
            return None
        if card.cover_url:
            return card
        card.cover_url = cover_url[:500]
        return await self.card_repo.save(card)

    async def apply_edits(
        self,
        card_id: int,
        *,
        title: str,
        authors: str | None,
        description: str | None,
        page_count: int | None,
    ) -> PendingGroupCard:
        card = await self.get_pending(card_id)
        card.title = title[:255]
        card.authors = authors[:500] if authors else None
        card.description = description
        card.page_count = page_count
        return await self.card_repo.save(card)

    async def approve(self, card_id: int) -> tuple[PendingGroupCard, bool]:
        card = await self.get_pending(card_id)
        if not (card.title and card.title.strip()):
            raise PendingCardNeedsTitleError("Сначала укажите название книги.")

        user = await self.user_repo.get_by_id(card.user_id)
        if user is None:
            raise PendingCardNotFoundError("Автор карточки не найден.")

        claimed = await self.card_repo.claim(card.id, PendingGroupCard.STATUS_APPROVED)
        if claimed is None:
            raise PendingCardNotFoundError("Эта карточка уже разобрана или не найдена.")

        _, created = await ManualBookService(self.session).add(
            user,
            title=claimed.title or "",
            authors=claimed.authors,
            description=claimed.description,
            page_count=claimed.page_count,
            cover_url=claimed.cover_url,
        )
        return claimed, created

    async def reject(self, card_id: int) -> PendingGroupCard:
        claimed = await self.card_repo.claim(card_id, PendingGroupCard.STATUS_REJECTED)
        if claimed is None:
            raise PendingCardNotFoundError("Эта карточка уже разобрана или не найдена.")
        return claimed


def format_card_preview(card: PendingGroupCard) -> str:
    title = card.title or "не распознано"
    authors = card.authors or "не указан"
    pages = str(card.page_count) if card.page_count is not None else "не указан"
    description = card.description or "нет"
    return (
        "Ручная карточка из группы. Проверьте поля перед голосованием.\n"
        f"Название: {title}\n"
        f"Автор: {authors}\n"
        f"Страницы: {pages}\n"
        f"Описание: {description}"
    )
