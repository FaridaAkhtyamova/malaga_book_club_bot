from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import PollOption

from app.core.config import get_settings
from app.db.models import Book, SuggestionCycle
from app.services.cycle_service import MONTH_NAMES_RU
from app.services.meeting_invite import (
    MONTH_GENITIVE_RU,
    InvalidMeetingDateError,
    bare_book_title,
    parse_meeting_date,
)

DATE_OPTION_COUNT = 10
DATE_OFFSET_DAYS = 2
TIME_START_HOUR = 10
TIME_END_HOUR = 19
OPTION_UNREAD = "не прочитала"
OPTION_SKIP = "пропущу"
POLL_QUESTION_LIMIT = 300
POLL_MAX_OPTIONS = 10
MIN_RUNOFF_DATES = 2

WEEKDAYS_RU: tuple[str, ...] = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)

_DATE_WEEKDAY = re.compile(r"^(\d{1,2}),\s+(.+)$")


@dataclass(frozen=True, slots=True)
class MeetingDateOption:
    label: str
    day: date | None


@dataclass(frozen=True, slots=True)
class MeetingTimeOption:
    label: str
    hour: int


@dataclass(frozen=True, slots=True)
class DateVoteCounts:
    by_date: dict[date, int]

    @property
    def total(self) -> int:
        return sum(self.by_date.values())

    def leaders(self) -> list[date]:
        if not self.by_date:
            return []
        top = max(self.by_date.values())
        if top <= 0:
            return []
        return [day for day, votes in self.by_date.items() if votes == top]


@dataclass(frozen=True, slots=True)
class HourVoteCounts:
    by_hour: dict[int, int]

    @property
    def total(self) -> int:
        return sum(self.by_hour.values())

    def leaders(self) -> list[int]:
        if not self.by_hour:
            return []
        top = max(self.by_hour.values())
        if top <= 0:
            return []
        return [hour for hour, votes in self.by_hour.items() if votes == top]


def meeting_poll_title(book: Book) -> str:
    return book.title.strip() or "книга месяца"


def format_manual_meeting_title(raw: str) -> str:
    text = bare_book_title(raw)
    if not text:
        return text
    return " ".join(word[0].upper() + word[1:] if word else word for word in text.split())


def meeting_subject(cycle: SuggestionCycle, book: Book | None = None) -> str:
    override = (cycle.meeting_title or "").strip()
    if override:
        return override
    if book is not None:
        return meeting_poll_title(book)
    return f"книга на {MONTH_NAMES_RU[cycle.target_month]}"


def meeting_poll_question(title: str) -> str:
    prefix = "📅 Когда встречаемся по «"
    suffix = "»?"
    budget = POLL_QUESTION_LIMIT - len(prefix) - len(suffix)
    if len(title) > budget:
        title = f"{title[: max(budget - 1, 1)]}…"
    return f"{prefix}{title}{suffix}"


def meeting_poll_intro(title: str) -> str:
    return (
        f"📅 Голосуем за дату встречи по «{title}». "
        "Можно выбрать несколько дней, отметить «не прочитала» или «пропущу», "
        "и добавить свой вариант. Опрос неанонимный."
    )


def meeting_date_runoff_intro() -> str:
    return (
        "🔁 Ничья. Голосуем ещё раз — только дни с одинаковым числом голосов. "
        "Опрос неанонимный, один вариант."
    )


def meeting_date_runoff_question() -> str:
    return "📅 Дата встречи — второй тур"


def meeting_poll_options(now: datetime | None = None) -> list[MeetingDateOption]:
    start = _localized_today(now) + timedelta(days=DATE_OFFSET_DAYS)
    dates = [
        MeetingDateOption(
            _format_date_option(start + timedelta(days=offset)),
            start + timedelta(days=offset),
        )
        for offset in range(DATE_OPTION_COUNT)
    ]
    return [
        *dates,
        MeetingDateOption(OPTION_UNREAD, None),
        MeetingDateOption(OPTION_SKIP, None),
    ]


def meeting_runoff_options(days: Sequence[date]) -> list[MeetingDateOption]:
    unique = list(dict.fromkeys(days))
    return [MeetingDateOption(_format_date_option(day), day) for day in unique]


def option_date_isos(choices: Sequence[MeetingDateOption]) -> list[str | None]:
    return [choice.day.isoformat() if choice.day is not None else None for choice in choices]


def option_labels(choices: Sequence[MeetingDateOption | MeetingTimeOption]) -> list[str]:
    return [choice.label for choice in choices]


def chunk_dates_for_polls(
    days: Sequence[date],
    *,
    max_size: int = POLL_MAX_OPTIONS,
) -> list[list[date]]:
    remaining = list(days)
    if len(remaining) < MIN_RUNOFF_DATES:
        return []
    if len(remaining) <= max_size:
        return [remaining]

    chunks: list[list[date]] = []
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


def tally_meeting_dates(
    stored_dates: Sequence[str | None],
    options: Sequence[PollOption],
    *,
    now: datetime | None = None,
) -> DateVoteCounts:
    counts: dict[date, int] = {}
    for index, option in enumerate(options):
        day: date | None = None
        stored = stored_dates[index] if index < len(stored_dates) else None
        if stored:
            day = date.fromisoformat(stored)
        else:
            day = parse_custom_date_option(option.text, now=now)
        if day is None:
            continue
        counts[day] = counts.get(day, 0) + option.voter_count
    return DateVoteCounts(by_date=counts)


def merge_date_counts(parts: Sequence[DateVoteCounts]) -> DateVoteCounts:
    merged: dict[date, int] = {}
    for part in parts:
        for day, votes in part.by_date.items():
            merged[day] = merged.get(day, 0) + votes
    return DateVoteCounts(by_date=merged)


def parse_custom_date_option(text: str, *, now: datetime | None = None) -> date | None:
    stripped = text.strip()
    if stripped.casefold() in {OPTION_UNREAD, OPTION_SKIP}:
        return None

    weekday_match = _DATE_WEEKDAY.fullmatch(stripped)
    if weekday_match is not None:
        day_num = int(weekday_match.group(1))
        weekday_name = weekday_match.group(2).strip().casefold()
        try:
            weekday = WEEKDAYS_RU.index(weekday_name)
        except ValueError:
            return None
        start = _localized_today(now)
        for offset in range(0, 62):
            candidate = start + timedelta(days=offset)
            if candidate.day == day_num and candidate.weekday() == weekday:
                return candidate
        return None

    try:
        return parse_meeting_date(stripped, now=now)
    except InvalidMeetingDateError:
        return None


def format_meeting_day(day: date) -> str:
    weekday = WEEKDAYS_RU[day.weekday()]
    return f"{day.day} {MONTH_GENITIVE_RU[day.month]} ({weekday})"


def meeting_date_announcement(
    cycle: SuggestionCycle,
    book: Book | None,
    day: date,
) -> str:
    title = meeting_poll_title(book) if book is not None else meeting_subject(cycle)
    return f"📅 Встреча по «{title}»: {format_meeting_day(day)}."


def meeting_date_admin_prompt(book: Book | None, day: date) -> str:
    formatted = format_meeting_day(day)
    weekend = day.weekday() >= 5
    if book is None:
        prompt = (
            f"Дата встречи выбрана: {formatted}.\n"
            "Напишите /create_meeting, затем название книги и время — "
            "опубликуется приглашение в календарь."
        )
    else:
        prompt = (
            f"Дата встречи по «{meeting_poll_title(book)}»: {formatted}.\n"
            "Напишите /create_meeting и укажите время — "
            "опубликуется приглашение в календарь."
        )
    if weekend:
        return (
            f"{prompt}\n"
            "На выходных время можно выбрать опросом: /start_meeting_time_poll."
        )
    return f"{prompt}\nВ будни встреча обычно в 19:00."


def meeting_time_poll_question(title: str) -> str:
    prefix = "🕐 Во сколько встречаемся по «"
    suffix = "»?"
    budget = POLL_QUESTION_LIMIT - len(prefix) - len(suffix)
    if len(title) > budget:
        title = f"{title[: max(budget - 1, 1)]}…"
    return f"{prefix}{title}{suffix}"


def meeting_time_poll_intro(title: str, day: date | None = None) -> str:
    when = f" {format_meeting_day(day)}" if day is not None else ""
    return (
        f"🕐 Голосуем за время встречи{when} по «{title}». "
        "Можно выбрать несколько часов. Опрос неанонимный."
    )


def meeting_time_runoff_intro() -> str:
    return (
        "🔁 Ничья. Голосуем ещё раз — только часы с одинаковым числом голосов. "
        "Опрос неанонимный, один вариант."
    )


def meeting_time_runoff_question() -> str:
    return "🕐 Время встречи — второй тур"


def format_meeting_hour(hour: int) -> str:
    return f"{hour:02d}:00"


def meeting_time_poll_options() -> list[MeetingTimeOption]:
    return [
        MeetingTimeOption(format_meeting_hour(hour), hour)
        for hour in range(TIME_START_HOUR, TIME_END_HOUR + 1)
    ]


def meeting_time_runoff_options(hours: Sequence[int]) -> list[MeetingTimeOption]:
    unique = list(dict.fromkeys(hours))
    return [MeetingTimeOption(format_meeting_hour(hour), hour) for hour in unique]


def option_hours(choices: Sequence[MeetingTimeOption]) -> list[int]:
    return [choice.hour for choice in choices]


def chunk_hours_for_polls(
    hours: Sequence[int],
    *,
    max_size: int = POLL_MAX_OPTIONS,
) -> list[list[int]]:
    remaining = list(hours)
    if len(remaining) < MIN_RUNOFF_DATES:
        return []
    if len(remaining) <= max_size:
        return [remaining]

    chunks: list[list[int]] = []
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


def tally_meeting_hours(
    stored_hours: Sequence[int],
    options: Sequence[PollOption],
) -> HourVoteCounts:
    counts: dict[int, int] = {}
    for index, option in enumerate(options):
        if index >= len(stored_hours):
            continue
        hour = stored_hours[index]
        counts[hour] = counts.get(hour, 0) + option.voter_count
    return HourVoteCounts(by_hour=counts)


def merge_hour_counts(parts: Sequence[HourVoteCounts]) -> HourVoteCounts:
    merged: dict[int, int] = {}
    for part in parts:
        for hour, votes in part.by_hour.items():
            merged[hour] = merged.get(hour, 0) + votes
    return HourVoteCounts(by_hour=merged)


def meeting_time_announcement(
    cycle: SuggestionCycle,
    book: Book | None,
    day: date | None,
    hour: int,
) -> str:
    title = meeting_poll_title(book) if book is not None else meeting_subject(cycle)
    clock = format_meeting_hour(hour)
    if day is None:
        return f"📅 Встреча по «{title}»: {clock}."
    return f"📅 Встреча по «{title}»: {format_meeting_day(day)}, {clock}."


def meeting_time_admin_prompt(book: Book | None, day: date | None, hour: int) -> str:
    clock = format_meeting_hour(hour)
    when = f"{format_meeting_day(day)}, {clock}" if day is not None else clock
    if book is None:
        return (
            f"Время встречи выбрано: {when}.\n"
            "Напишите /create_meeting — опубликуется приглашение в календарь."
        )
    return (
        f"Время встречи по «{meeting_poll_title(book)}»: {when}.\n"
        "Напишите /create_meeting — опубликуется приглашение в календарь."
    )


def _localized_today(now: datetime | None) -> date:
    tz = ZoneInfo(get_settings().TIMEZONE)
    if now is None:
        current = datetime.now(tz)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=tz)
    else:
        current = now.astimezone(tz)
    return current.date()


def _format_date_option(day: date) -> str:
    return f"{day.day:02d}.{day.month:02d}"
