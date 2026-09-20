from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from app.core.config import get_settings

MEETING_DURATION = timedelta(minutes=90)
ICS_FILENAME = "knizhny-klub.ics"

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
    google_url: str
    outlook_url: str
    filename: str = ICS_FILENAME


def event_title(book_title: str) -> str:
    return f"книжный клуб {book_title}"


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
        google_url=_google_calendar_url(title, start, end),
        outlook_url=_outlook_calendar_url(title, start, end),
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


def _ics_bytes(title: str, start: datetime, end: datetime) -> bytes:
    stamp = _utc_stamp(datetime.now(UTC))
    uid = f"{uuid.uuid4()}@malaga-book-club"
    description = _ics_escape(f"{title}\nМалага")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Malaga Book Club Bot//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"CREATED:{stamp}",
        f"LAST-MODIFIED:{stamp}",
        f"DTSTART:{_utc_stamp(start)}",
        f"DTEND:{_utc_stamp(end)}",
        f"SUMMARY:{_ics_escape(title)}",
        f"DESCRIPTION:{description}",
        "LOCATION:Málaga",
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "TRANSP:OPAQUE",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Напоминание",
        "TRIGGER:-PT30M",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold_ics_line(line))
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")


def _invite_caption(title: str, start: datetime, end: datetime) -> str:
    local_start = start.astimezone(ZoneInfo(get_settings().TIMEZONE))
    local_end = end.astimezone(ZoneInfo(get_settings().TIMEZONE))
    month = MONTH_GENITIVE_RU[local_start.month]
    when = f"{local_start.day} {month} {local_start.year}, {local_start:%H:%M}–{local_end:%H:%M}"
    return (
        f"🗓️ {title}\n{when} (Малага)\n\n"
        "iPhone: кнопка «В календарь» — файл .ics в Telegram часто не сохраняется.\n"
        "Android и компьютер: откройте файл .ics."
    )


def _google_calendar_url(title: str, start: datetime, end: datetime) -> str:
    tz_name = get_settings().TIMEZONE
    local_start = start.astimezone(ZoneInfo(tz_name))
    local_end = end.astimezone(ZoneInfo(tz_name))
    dates = f"{_local_stamp(local_start)}/{_local_stamp(local_end)}"
    query = urlencode(
        {
            "action": "TEMPLATE",
            "text": title,
            "dates": dates,
            "ctz": tz_name,
            "location": "Málaga",
        },
        quote_via=quote,
    )
    return f"https://calendar.google.com/calendar/render?{query}"


def _outlook_calendar_url(title: str, start: datetime, end: datetime) -> str:
    query = urlencode(
        {
            "rru": "addevent",
            "subject": title,
            "startdt": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "enddt": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "location": "Málaga",
        },
        quote_via=quote,
    )
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{query}"


def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _local_stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def _fold_ics_line(line: str) -> list[str]:
    remaining = line.encode("utf-8")
    parts: list[str] = []
    limit = 75
    while remaining:
        chunk = remaining[:limit]
        while chunk:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        if not chunk:
            chunk = remaining[:1]
        text = chunk.decode("utf-8")
        parts.append(text if not parts else f" {text}")
        remaining = remaining[len(chunk) :]
        limit = 74
    return parts


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")
