from __future__ import annotations

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Book, ClubSettings, MeetingPoll, SuggestionCycle, User, VotePoll
from app.repositories.book_repo import BookRepository
from app.repositories.cycle_repo import CycleRepository
from app.repositories.cycle_vote_repo import CycleVoteRepository
from app.repositories.meeting_poll_repo import MeetingPollRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.suggestion_repo import SuggestionRepository
from app.repositories.vote_poll_repo import VotePollRepository
from app.schemas.book import BookSchema

MONTH_NAMES_RU: dict[int, str] = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}

POLL_OPTION_LIMIT = 100
POLL_MAX_OPTIONS = 10
CAPTION_LIMIT = 1024
MIN_POLL_BOOKS = 2
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class CycleServiceError(Exception):
    """Base error for suggestion cycle operations."""


class GroupNotSetError(CycleServiceError):
    """Club group chat is not bound."""


class InvalidDayError(CycleServiceError):
    """Schedule day is out of range or inconsistent."""


class CycleAlreadyOpenError(CycleServiceError):
    """Suggestions for the target month are already open or finished."""


class CycleNotOpenError(CycleServiceError):
    """There is no cycle in SUGGESTING status."""


class NotEnoughBooksError(CycleServiceError):
    """Fewer than two books — Telegram poll cannot be created."""


class CycleNotVotingError(CycleServiceError):
    """There is no cycle in VOTING status."""


class NoOpenPollsError(CycleServiceError):
    """Voting is open but no Telegram polls are recorded as open."""


class VotePollsAlreadyOpenError(CycleServiceError):
    """This cycle already has live Telegram polls."""


class NoWinnerError(CycleServiceError):
    """The latest vote has not produced a winning book yet."""


class NoMeetingDateError(CycleServiceError):
    """The meeting-date poll has not produced a winning day yet."""


class MeetingPollsAlreadyOpenError(CycleServiceError):
    """This cycle already has a live meeting-date poll."""


class NoOpenMeetingPollsError(CycleServiceError):
    """There is no recorded meeting-date poll the bot can close."""


@dataclass(frozen=True, slots=True)
class ScheduledAnnounce:
    text: str


@dataclass(frozen=True, slots=True)
class ScheduledVote:
    cycle: SuggestionCycle
    chunks: list[list[Book]]


@dataclass(frozen=True, slots=True)
class PublishedVotePoll:
    chat_id: int
    message_id: int
    telegram_poll_id: str | None
    book_ids: list[int]


@dataclass(frozen=True, slots=True)
class PublishedMeetingPoll:
    chat_id: int
    message_id: int
    telegram_poll_id: str | None
    option_dates: list[str | None]


class CycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings_repo = SettingsRepository(session)
        self.cycle_repo = CycleRepository(session)
        self.cycle_vote_repo = CycleVoteRepository(session)
        self.suggestion_repo = SuggestionRepository(session)
        self.book_repo = BookRepository(session)
        self.vote_poll_repo = VotePollRepository(session)
        self.meeting_poll_repo = MeetingPollRepository(session)

    async def get_settings(self) -> ClubSettings:
        return await self.settings_repo.get_or_create()

    async def bind_group(self, chat_id: int) -> ClubSettings:
        settings = await self.settings_repo.get_or_create()
        settings.group_chat_id = chat_id
        return await self.settings_repo.save(settings)

    async def set_suggest_day(self, day: int) -> ClubSettings:
        _validate_day(day)
        settings = await self.settings_repo.get_or_create()
        if settings.vote_day is not None and day >= settings.vote_day:
            raise InvalidDayError("День предложений должен быть раньше дня голосования.")
        settings.suggest_day = day
        return await self.settings_repo.save(settings)

    async def set_vote_day(self, day: int) -> ClubSettings:
        _validate_day(day)
        settings = await self.settings_repo.get_or_create()
        if settings.suggest_day is not None and day <= settings.suggest_day:
            raise InvalidDayError("День голосования должен быть позже дня предложений.")
        settings.vote_day = day
        return await self.settings_repo.save(settings)

    async def is_club_group(self, chat_id: int) -> bool:
        settings = await self.settings_repo.get_or_create()
        return settings.group_chat_id is not None and settings.group_chat_id == chat_id

    async def get_active_suggesting_cycle(self) -> SuggestionCycle | None:
        return await self.cycle_repo.get_latest_suggesting()

    async def get_latest_cycle(self) -> SuggestionCycle | None:
        return await self.cycle_repo.get_latest()

    async def count_suggestions(self, cycle_id: int) -> int:
        return await self.suggestion_repo.count(cycle_id)

    async def open_suggestions_for_next_month(
        self,
        now: datetime | None = None,
    ) -> tuple[SuggestionCycle, str]:
        settings = await self.settings_repo.get_or_create()
        if settings.group_chat_id is None:
            raise GroupNotSetError("Сначала привяжите группу командой /set_group.")

        current = self._localized_now(now)
        year, month = next_year_month(current)
        existing = await self.cycle_repo.get_by_month(year, month)
        if existing is not None:
            raise CycleAlreadyOpenError("Сбор предложений на этот месяц уже был открыт.")

        cycle = await self.cycle_repo.create(year, month)
        return cycle, announcement_text(month)

    async def add_suggestion(
        self,
        user: User,
        book_schema: BookSchema,
    ) -> tuple[Book, bool]:
        cycle = await self.cycle_repo.get_latest_suggesting()
        if cycle is None:
            raise CycleNotOpenError("Предложения ещё не открыты.")

        book = await self.book_repo.get_or_create(book_schema)
        if await self.suggestion_repo.exists(cycle.id, book.id):
            return book, False

        created = await self.suggestion_repo.add(cycle.id, book.id, user.id)
        if created is None:
            return book, False
        return book, True

    async def prepare_vote(self) -> tuple[SuggestionCycle, list[list[Book]]]:
        cycle = await self.cycle_repo.get_latest_suggesting()
        if cycle is None:
            cycle = await self.cycle_vote_repo.get_latest_voting()
            if cycle is None:
                raise CycleNotOpenError("Сейчас нет открытого сбора предложений.")
            open_polls = await self.vote_poll_repo.list_open(cycle.id)
            if open_polls:
                raise VotePollsAlreadyOpenError(
                    "Опросы уже идут. Когда время вышло, закройте их командой /close_vote."
                )

        books = await self.suggestion_repo.list_books(cycle.id)
        chunks = chunk_books_for_polls(books)
        if not chunks:
            raise NotEnoughBooksError("Для опроса нужно минимум две предложенные книги.")
        return cycle, chunks

    async def mark_voting(self, cycle: SuggestionCycle) -> SuggestionCycle:
        return await self.cycle_repo.set_status(cycle, SuggestionCycle.STATUS_VOTING)

    async def record_vote_polls(
        self,
        cycle: SuggestionCycle,
        polls: Sequence[PublishedVotePoll],
    ) -> None:
        for poll in polls:
            await self.vote_poll_repo.add(
                cycle_id=cycle.id,
                chat_id=poll.chat_id,
                message_id=poll.message_id,
                telegram_poll_id=poll.telegram_poll_id,
                option_book_ids=poll.book_ids,
            )

    async def get_latest_voting(self) -> SuggestionCycle | None:
        return await self.cycle_vote_repo.get_latest_voting()

    async def require_open_vote_polls(self, cycle: SuggestionCycle) -> list[VotePoll]:
        if cycle.status != SuggestionCycle.STATUS_VOTING:
            raise CycleNotVotingError("Сейчас нет активного голосования за книгу.")
        polls = await self.vote_poll_repo.list_open(cycle.id)
        if not polls:
            raise NoOpenPollsError(
                "Нет опросов, которые бот может закрыть. "
                "Запустите /start_vote ещё раз — старые опросы в чате не считаются."
            )
        return polls

    async def mark_poll_closed(self, poll: VotePoll) -> None:
        await self.vote_poll_repo.mark_closed(poll)

    async def apply_winner(self, cycle: SuggestionCycle, book: Book) -> SuggestionCycle:
        return await self.cycle_vote_repo.set_winner(cycle, book.id)

    async def reopen_suggestions_after_empty_vote(
        self,
        cycle: SuggestionCycle,
    ) -> SuggestionCycle:
        return await self.cycle_repo.set_status(cycle, SuggestionCycle.STATUS_SUGGESTING)

    async def book_for_cycle(self, cycle: SuggestionCycle) -> Book | None:
        if cycle.winner_book_id is None:
            return None
        books = await self.book_repo.get_by_ids([cycle.winner_book_id])
        return books[0] if books else None

    async def get_selected_cycle(self) -> SuggestionCycle:
        cycle = await self.cycle_vote_repo.get_latest_with_winner()
        if cycle is None or cycle.winner is None:
            raise NoWinnerError(
                "Сначала закройте голосование за книгу командой /close_vote."
            )
        return cycle

    async def get_selected_book(self) -> Book:
        cycle = await self.get_selected_cycle()
        book = cycle.winner
        if book is None:
            raise NoWinnerError(
                "Сначала закройте голосование за книгу командой /close_vote."
            )
        return book

    async def get_selected_meeting(self) -> tuple[Book, date]:
        cycle = await self.get_selected_cycle()
        book = cycle.winner
        meeting_day = cycle.winner_meeting_date
        if book is None:
            raise NoWinnerError(
                "Сначала закройте голосование за книгу командой /close_vote."
            )
        if meeting_day is None:
            raise NoMeetingDateError(
                "Сначала закройте опрос дат командой /close_meeting_poll."
            )
        return book, meeting_day

    async def prepare_meeting_poll(self) -> SuggestionCycle:
        cycle = await self.get_latest_cycle()
        if cycle is None:
            raise CycleNotOpenError("Сначала откройте сбор командой /open_suggestions.")
        open_polls = await self.meeting_poll_repo.list_open(cycle.id)
        if open_polls:
            raise MeetingPollsAlreadyOpenError(
                "Опрос дат уже идёт. Когда время вышло, закройте его командой /close_meeting_poll."
            )
        if cycle.winner_meeting_date is not None:
            await self.cycle_vote_repo.clear_meeting_date(cycle)
        return cycle

    async def get_meeting_poll_cycle(self) -> SuggestionCycle:
        cycle = await self.get_latest_cycle()
        if cycle is None:
            raise CycleNotOpenError("Сначала откройте сбор командой /open_suggestions.")
        return cycle

    async def record_meeting_poll(self, cycle: SuggestionCycle, poll: PublishedMeetingPoll) -> None:
        await self.meeting_poll_repo.add(
            cycle_id=cycle.id,
            chat_id=poll.chat_id,
            message_id=poll.message_id,
            telegram_poll_id=poll.telegram_poll_id,
            option_dates=poll.option_dates,
        )

    async def require_open_meeting_polls(self, cycle: SuggestionCycle) -> list[MeetingPoll]:
        polls = await self.meeting_poll_repo.list_open(cycle.id)
        if not polls:
            raise NoOpenMeetingPollsError(
                "Нет опроса дат, который бот может закрыть. "
                "Запустите /start_meeting_poll ещё раз — старый опрос в чате не считается."
            )
        return polls

    async def mark_meeting_poll_closed(self, poll: MeetingPoll) -> None:
        await self.meeting_poll_repo.mark_closed(poll)

    async def apply_meeting_date(
        self,
        cycle: SuggestionCycle,
        meeting_day: date,
    ) -> SuggestionCycle:
        return await self.cycle_vote_repo.set_meeting_date(cycle, meeting_day)

    async def books_by_ids(self, ids: Sequence[int]) -> list[Book]:
        return await self.book_repo.get_by_ids(ids)

    async def run_scheduled(self, now: datetime) -> ScheduledAnnounce | ScheduledVote | None:
        settings = await self.settings_repo.get_or_create()
        if settings.group_chat_id is None:
            return None

        current = self._localized_now(now)
        if current.hour < settings.announce_hour:
            return None

        if settings.suggest_day is not None and current.day == settings.suggest_day:
            year, month = next_year_month(current)
            existing = await self.cycle_repo.get_by_month(year, month)
            if existing is None:
                _, text = await self.open_suggestions_for_next_month(current)
                return ScheduledAnnounce(text=text)

        if settings.vote_day is not None and current.day == settings.vote_day:
            cycle = await self.cycle_repo.get_latest_suggesting()
            if cycle is not None:
                try:
                    vote_cycle, chunks = await self.prepare_vote()
                except NotEnoughBooksError:
                    return None
                return ScheduledVote(cycle=vote_cycle, chunks=chunks)

        return None

    def _localized_now(self, now: datetime | None) -> datetime:
        tz = ZoneInfo(get_settings().TIMEZONE)
        if now is None:
            return datetime.now(tz)
        if now.tzinfo is None:
            return now.replace(tzinfo=tz)
        return now.astimezone(tz)


def next_year_month(now: datetime) -> tuple[int, int]:
    if now.month == 12:
        return now.year + 1, 1
    return now.year, now.month + 1


def month_name_ru(month: int) -> str:
    return MONTH_NAMES_RU[month]


def announcement_text(month: int) -> str:
    return f"Дорогой клуб, начинаем предлагать книги на {month_name_ru(month)}."


def poll_intro_text() -> str:
    return (
        "Голосуем за книгу месяца. Опросы неанонимные. "
        "Если опросов несколько, можно проголосовать в каждом."
    )


def poll_question(month: int, index: int, total: int) -> str:
    name = month_name_ru(month)
    if total == 1:
        return f"Книга на {name}"
    return f"Книга на {name} ({index}/{total})"


def format_poll_option(book: Book, used: set[str]) -> str:
    authors = book.authors or "автор не указан"
    label = f"{book.title} — {authors}"
    if len(label) > POLL_OPTION_LIMIT:
        label = f"{label[: POLL_OPTION_LIMIT - 1]}…"
    if label in used:
        suffix = f" [{book.id}]"
        budget = POLL_OPTION_LIMIT - len(suffix)
        label = f"{label[:budget]}{suffix}"
    used.add(label)
    return label


def chunk_books_for_polls(
    books: Sequence[Book],
    *,
    max_size: int = POLL_MAX_OPTIONS,
) -> list[list[Book]]:
    if len(books) < MIN_POLL_BOOKS:
        return []

    remaining = list(books)
    if len(remaining) <= max_size:
        return [remaining]

    chunks: list[list[Book]] = []
    while remaining:
        if len(remaining) <= max_size:
            if len(remaining) == 1:
                previous = chunks[-1]
                moved = previous.pop()
                chunks.append([moved, remaining[0]])
            else:
                chunks.append(remaining)
            break
        chunks.append(remaining[:max_size])
        remaining = remaining[max_size:]
    return chunks


def format_book_card(book: Book, suggester: User) -> str:
    title = html.escape(book.title)
    authors = html.escape(book.authors or "автор не указан")
    pages = f"{book.page_count} стр." if book.page_count else "объём не указан"
    if suggester.username:
        who = f"@{html.escape(suggester.username)}"
    else:
        who = html.escape(suggester.full_name or str(suggester.id))

    header = f"<b>{title}</b>\n{authors}\n{html.escape(pages)}\nПредложил(а): {who}"
    description = _plain_description(book.description)
    if not description:
        return header

    separator = "\n\n"
    remaining = CAPTION_LIMIT - len(header) - len(separator)
    fitted = _fit_html_text(description, remaining)
    if not fitted:
        return header
    return f"{header}{separator}{fitted}"


def _validate_day(day: int) -> None:
    if not 1 <= day <= 28:
        raise InvalidDayError("День должен быть от 1 до 28.")


def _plain_description(raw: str | None) -> str:
    if not raw:
        return ""
    return _HTML_TAG_RE.sub("", raw).strip()


def _fit_html_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    escaped = html.escape(text)
    if len(escaped) <= limit:
        return escaped
    if limit <= 1:
        return "…"[:limit]

    cut = min(len(text), limit)
    while cut > 0:
        candidate = html.escape(text[:cut]) + "…"
        if len(candidate) <= limit:
            return candidate
        cut -= 1
    return ""
