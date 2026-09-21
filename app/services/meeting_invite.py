from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

MEETING_DURATION = timedelta(minutes=90)
ICS_FILENAME = "event.ics"
ICS_CONTENT_TYPE = "text/calendar; charset=utf-8"

_DATE_FULL = re.compile(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$")
_DATE_SHORT = re.compile(r"^(\d{1,2})[./](\d{1,2})$")
_TIME = re.compile(r"^(\d{1,2})[:.](\d{2})$")

MONTH_GENITIVE_RU: dict[int, str] = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


class MeetingInviteError(Exception):
    """Invalid meeting date or time from the admin."""


class InvalidMeetingDateError(MeetingInviteError):
    """Date text cannot be parsed or is not a real calendar day."""


class InvalidMeetingTimeError(MeetingInviteError):
    """Time text cannot be parsed."""


class MeetingInPastError(MeetingInviteError):
    """Combined date and time are not in the future."""


@dataclass(frozen=True, slots=True)
class MeetingInvite:
    title: str
    start: datetime
    end: datetime
    ics_bytes: bytes
    caption: str
    filename: str = ICS_FILENAME


def event_title(book_title: str) -> str:
    return f"Книжный Клуб: {_bare_book_title(book_title)}"


def parse_meeting_date(raw: str, *, now: datetime | None = None) -> date:
    text = raw.strip()
    full = _DATE_FULL.fullmatch(text)
    if full is not None:
        return _valid_date(int(full.group(1)), int(full.group(2)), int(full.group(3)))

    short = _DATE_SHORT.fullmatch(text)
    if short is not None:
        current = _localized_now(now)
        return _valid_date(int(short.group(1)), int(short.group(2)), current.year)

    raise InvalidMeetingDateError("Напишите дату как 25.09 или 25.09.2026.")


def parse_meeting_time(raw: str) -> tuple[int, int]:
    match = _TIME.fullmatch(raw.strip())
    if match is None:
        raise InvalidMeetingTimeError("Напишите время как 19:00.")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise InvalidMeetingTimeError("Напишите время как 19:00.")
    return hour, minute


def build_meeting_start(
    meeting_day: date,
    hour: int,
    minute: int,
    *,
    now: datetime | None = None,
) -> datetime:
    tz = ZoneInfo(get_settings().TIMEZONE)
    start = datetime(
        meeting_day.year,
        meeting_day.month,
        meeting_day.day,
        hour,
        minute,
        tzinfo=tz,
    )
    current = _localized_now(now)
    if start <= current:
        raise MeetingInPastError("Эта дата и время уже прошли. Напишите дату ещё раз.")
    return start


def build_meeting_invite(start: datetime, *, book_title: str) -> MeetingInvite:
    title = event_title(book_title)
    end = start + MEETING_DURATION
    return MeetingInvite(
        title=title,
        start=start,
        end=end,
        ics_bytes=_ics_bytes(title, start, end),
        caption=_invite_caption(title, start, end),
    )


def _localized_now(now: datetime | None) -> datetime:
    tz = ZoneInfo(get_settings().TIMEZONE)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _valid_date(day: int, month: int, year: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise InvalidMeetingDateError("Такой даты нет.") from exc


def _bare_book_title(book_title: str) -> str:
    text = book_title.strip()
    if len(text) >= 2 and (
        (text.startswith("«") and text.endswith("»"))
        or (text[0] == text[-1] and text[0] in {'"', "'"})
    ):
        return text[1:-1].strip()
    return text


def _when_line(start: datetime, end: datetime) -> str:
    tz = ZoneInfo(get_settings().TIMEZONE)
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    month = MONTH_GENITIVE_RU[local_start.month]
    return (
        f"{local_start.day} {month} {local_start.year}, "
        f"{local_start:%H:%M}–{local_end:%H:%M} (Малага)"
    )


def _ics_bytes(title: str, start: datetime, end: datetime) -> bytes:
    tz = ZoneInfo(get_settings().TIMEZONE)
    local_start = start.astimezone(tz)
    uid = f"bookclub-{local_start.strftime('%Y%m%d-%H%M%S')}@malagabookclub"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Malaga Book Club Bot//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_utc_stamp(datetime.now(UTC))}",
        f"SUMMARY:{_ics_escape(title)}",
        f"LOCATION:{_ics_escape('Málaga')}",
        f"DTSTART:{_utc_stamp(start)}",
        f"DTEND:{_utc_stamp(end)}",
        "BEGIN:VALARM",
        "TRIGGER:-PT1H",
        "ACTION:DISPLAY",
        "DESCRIPTION:Напоминание",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def _invite_caption(title: str, start: datetime, end: datetime) -> str:
    return f"🗓️ {_quoted_display_title(title)}\n{_when_line(start, end)}"


def _quoted_display_title(title: str) -> str:
    prefix = "Книжный Клуб: "
    if title.startswith(prefix):
        return f'{prefix}"{title.removeprefix(prefix)}"'
    return title


def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")
