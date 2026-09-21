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
        "24 сентября 2026, 19:00–20:30 (Малага)\n\n"
        "iPhone: нажмите «Добавить в календарь»."
    )
    assert invite.filename == "event.ics"


def test_ics_matches_iphone_event_template() -> None:
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Винни-Пух и все-все-все")
    text = invite.ics_bytes.decode("utf-8")

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert "VERSION:2.0\r\n" in text
    assert "PRODID:-//Malaga Book Club Bot//EN\r\n" in text
    assert "CALSCALE:GREGORIAN\r\n" in text
    assert "METHOD:PUBLISH\r\n" in text
    assert "UID:bookclub-20260924-190000@malagabookclub\r\n" in text
    assert re.search(r"DTSTAMP:\d{8}T\d{6}Z\r\n", text)
    assert "SUMMARY:Книжный Клуб: Винни-Пух и все-все-все\r\n" in text
    assert "LOCATION:Málaga\r\n" in text
    assert "DTSTART:20260924T170000Z\r\n" in text
    assert "DTEND:20260924T183000Z\r\n" in text
    assert "TZID=" not in text
    assert "TRIGGER:-PT1H\r\n" in text
    assert "BEGIN:VTIMEZONE" not in text
    assert b"\r\n " not in invite.ics_bytes
    assert text.endswith("END:VCALENDAR\r\n")
    assert invite.filename == ICS_FILENAME == "event.ics"


def test_ics_converts_madrid_wall_clock_to_utc() -> None:
    start = datetime(2026, 9, 24, 11, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Винни-Пух и все-все-все")
    text = invite.ics_bytes.decode("utf-8")

    assert "UID:bookclub-20260924-110000@malagabookclub" in text
    assert "DTSTART:20260924T090000Z" in text
    assert "DTEND:20260924T103000Z" in text

    winter = datetime(2026, 12, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    winter_text = build_meeting_invite(winter, book_title="Dune").ics_bytes.decode("utf-8")
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


def test_calendar_button_uses_calndr_apple_link() -> None:
    start = datetime(2026, 9, 20, 19, 30, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Четвертое крыло")

    assert invite.ics_url.startswith("https://calndr.link/d/event/?")
    assert "service=apple" in invite.ics_url
    assert "start=2026-09-20T19%3A30%3A00" in invite.ics_url
    assert "end=2026-09-20T21%3A00%3A00" in invite.ics_url
    assert "timezone=Europe%2FMadrid" in invite.ics_url
    assert "title=" in invite.ics_url


def test_public_ics_url_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "PUBLIC_BASE_URL", "https://cal.example")
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")

    from app.services.meeting_invite import encode_invite_token, invite_from_token

    token = encode_invite_token(invite.title, invite.start)
    restored = invite_from_token(token)
    assert restored is not None
    assert restored.title == invite.title
    assert restored.start == invite.start
    assert "DTSTART:20260924T170000Z" in restored.ics_bytes.decode("utf-8")


async def test_ics_http_serves_text_calendar() -> None:
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")

    from aiohttp.test_utils import TestClient, TestServer

    from app.http.calendar import create_calendar_app
    from app.services.meeting_invite import ICS_CONTENT_TYPE, encode_invite_token

    token = encode_invite_token(invite.title, invite.start)
    app = create_calendar_app()
    async with TestClient(TestServer(app)) as client:
        response = await client.get(f"/invite/{token}.ics")
        assert response.status == 200
        assert response.headers["Content-Type"] == ICS_CONTENT_TYPE
        assert "event.ics" in response.headers["Content-Disposition"]
        body = await response.read()
        text = body.decode("utf-8")
        assert "BEGIN:VCALENDAR" in text
        assert "DTSTART:20260924T170000Z" in text

        missing = await client.get("/invite/not-a-token.ics")
        assert missing.status == 404
