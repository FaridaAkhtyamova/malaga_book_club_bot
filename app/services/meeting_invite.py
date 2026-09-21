from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

MEETING_DURATION = timedelta(minutes=90)
ICS_FILENAME = "event.ics"
ICS_CONTENT_TYPE = "text/calendar; charset=utf-8"
_TOKEN_SIG_LEN = 24

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
    ics_url: str | None
    filename: str = ICS_FILENAME


def event_title(book_title: str) -> str:
    return f'Книжный Клуб: "{_bare_book_title(book_title)}"'


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
    return build_meeting_invite_from_event(title=event_title(book_title), start=start)


def public_ics_url(title: str, start: datetime) -> str | None:
    base = get_settings().PUBLIC_BASE_URL
    if base is None:
        return None
    return f"{base}/invite/{encode_invite_token(title, start)}.ics"


def encode_invite_token(title: str, start: datetime) -> str:
    payload = json.dumps(
        {"t": title, "s": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_token_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature[:_TOKEN_SIG_LEN]}"


def invite_from_token(token: str) -> MeetingInvite | None:
    parsed = _decode_invite_token(token)
    if parsed is None:
        return None
    title, start = parsed
    return build_meeting_invite_from_event(title=title, start=start)


def build_meeting_invite_from_event(*, title: str, start: datetime) -> MeetingInvite:
    end = start + MEETING_DURATION
    return MeetingInvite(
        title=title,
        start=start,
        end=end,
        ics_bytes=_ics_bytes(title, start, end),
        caption=_invite_caption(title, start, end),
        ics_url=public_ics_url(title, start),
    )


def _decode_invite_token(token: str) -> tuple[str, datetime] | None:
    body, separator, signature = token.partition(".")
    if not separator or not body or not signature:
        return None
    expected = hmac.new(_token_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if len(signature) != _TOKEN_SIG_LEN:
        return None
    if not hmac.compare_digest(signature, expected[:_TOKEN_SIG_LEN]):
        return None
    padding = "=" * (-len(body) % 4)
    try:
        raw = json.loads(base64.urlsafe_b64decode(body + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    title = raw.get("t")
    start_raw = raw.get("s")
    if not isinstance(title, str) or not isinstance(start_raw, str):
        return None
    try:
        start = datetime.strptime(start_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return title, start


def _token_key() -> bytes:
    return get_settings().BOT_TOKEN.encode("utf-8")


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
    tz_name = get_settings().TIMEZONE
    tz = ZoneInfo(tz_name)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Malaga Book Club Bot//EN",
        "BEGIN:VEVENT",
        f"SUMMARY:{_ics_escape(title)}",
        f"LOCATION:{_ics_escape('Málaga')}",
        f"DTSTART;TZID={tz_name}:{_local_stamp(start.astimezone(tz))}",
        f"DTEND;TZID={tz_name}:{_local_stamp(end.astimezone(tz))}",
        "BEGIN:VALARM",
        "TRIGGER:-PT1H",
        "ACTION:DISPLAY",
        "DESCRIPTION:Напоминание",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    folded: list[str] = []
    for line in lines:
        folded.extend(_fold_ics_line(line))
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")


def _invite_caption(title: str, start: datetime, end: datetime) -> str:
    return (
        f"🗓️ {title}\n{_when_line(start, end)}\n\n"
        "Нажмите на файл, чтобы добавить запись в календарь."
    )


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
