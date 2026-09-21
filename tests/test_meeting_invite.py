import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import get_settings
from app.services.meeting_invite import ICS_FILENAME, build_meeting_invite, event_title


@pytest.fixture(autouse=True)
def madrid_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "TIMEZONE", "Europe/Madrid")


def test_event_title_does_not_quote_book_name() -> None:
    assert event_title("Винни-Пух и все-все-все") == "Книжный Клуб: Винни-Пух и все-все-все"
    assert event_title("«Dune»") == "Книжный Клуб: Dune"


def test_invite_caption_shows_quoted_title_and_malaga_time() -> None:
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Винни-Пух и все-все-все")
    assert invite.caption == (
        '🗓️ Книжный Клуб: "Винни-Пух и все-все-все"\n'
        "24 сентября 2026, 19:00–20:30 (Малага)"
    )
    assert invite.filename == "event.ics"


def test_ics_matches_iphone_event_template() -> None:
    start = datetime(2026, 9, 24, 11, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Винни-Пух и все-все-все")
    text = invite.ics_bytes.decode("utf-8")

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert "VERSION:2.0\r\n" in text
    assert "PRODID:-//Malaga Book Club Bot//EN\r\n" in text
    assert "CALSCALE:GREGORIAN\r\n" in text
    assert "METHOD:PUBLISH\r\n" in text
    assert "UID:bookclub-20260924-110000@malagabookclub\r\n" in text
    assert re.search(r"DTSTAMP:\d{8}T\d{6}Z\r\n", text)
    assert "SUMMARY:Книжный Клуб: Винни-Пух и все-все-все\r\n" in text
    assert "LOCATION:Málaga\r\n" in text
    assert "DTSTART:20260924T090000Z\r\n" in text
    assert "DTEND:20260924T103000Z\r\n" in text
    assert "TZID=" not in text
    assert "TRIGGER:-PT1H\r\n" in text
    assert "BEGIN:VTIMEZONE" not in text
    assert b"\r\n " not in invite.ics_bytes
    assert text.endswith("END:VCALENDAR\r\n")
    assert invite.filename == ICS_FILENAME == "event.ics"


def test_ics_converts_madrid_wall_clock_to_utc() -> None:
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    winter = datetime(2026, 12, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    summer_text = build_meeting_invite(start, book_title="Dune").ics_bytes.decode("utf-8")
    winter_text = build_meeting_invite(winter, book_title="Dune").ics_bytes.decode("utf-8")

    assert "DTSTART:20260924T170000Z" in summer_text
    assert "DTEND:20260924T183000Z" in summer_text
    assert "DTSTART:20261225T180000Z" in winter_text
    assert "DTEND:20261225T193000Z" in winter_text


def test_ics_keeps_summary_on_one_line() -> None:
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Винни-Пух и все-все-все")
    lines = invite.ics_bytes.decode("utf-8").split("\r\n")

    assert "SUMMARY:Книжный Клуб: Винни-Пух и все-все-все" in lines
    assert not any(line.startswith(" ") for line in lines)


def test_ics_upload_uses_text_calendar_mime() -> None:
    from app.bot.telegram_session import document_upload_fields
    from app.services.meeting_invite import ICS_CONTENT_TYPE

    assert document_upload_fields("event.ics") == {
        "filename": "event.ics",
        "content_type": ICS_CONTENT_TYPE,
    }
    assert document_upload_fields("cover.jpg") == {"filename": "cover.jpg"}
