from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import get_settings
from app.services.meeting_invite import ICS_FILENAME, build_meeting_invite, event_title


@pytest.fixture(autouse=True)
def madrid_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "TIMEZONE", "Europe/Madrid")


def test_event_title_quotes_book_name() -> None:
    assert event_title("Винни-Пух и все-все-все") == (
        'Книжный Клуб: "Винни-Пух и все-все-все"'
    )
    assert event_title("«Dune»") == 'Книжный Клуб: "Dune"'


def test_invite_caption_shows_quoted_title_and_malaga_time() -> None:
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Винни-Пух и все-все-все")
    assert invite.caption == (
        '🗓️ Книжный Клуб: "Винни-Пух и все-все-все"\n'
        "24 сентября 2026, 19:00–20:30 (Малага)\n\n"
        "Нажмите на файл, чтобы добавить запись в календарь."
    )
    assert invite.filename == "event.ics"


def test_ics_matches_iphone_event_template() -> None:
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    text = invite.ics_bytes.decode("utf-8")

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert "VERSION:2.0" in text
    assert "PRODID:-//Malaga Book Club Bot//EN" in text
    assert "METHOD:" not in text
    assert "BEGIN:VTIMEZONE" not in text
    assert 'SUMMARY:Книжный Клуб: "Dune"' in text
    assert "LOCATION:Málaga" in text
    assert "DTSTART;TZID=Europe/Madrid:20260925T190000" in text
    assert "DTEND;TZID=Europe/Madrid:20260925T203000" in text
    assert "TRIGGER:-PT1H" in text
    assert text.endswith("END:VCALENDAR\r\n")
    assert invite.filename == ICS_FILENAME == "event.ics"


def test_ics_keeps_winter_madrid_wall_clock() -> None:
    start = datetime(2026, 12, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    text = invite.ics_bytes.decode("utf-8")

    assert "DTSTART;TZID=Europe/Madrid:20261225T190000" in text
    assert "DTEND;TZID=Europe/Madrid:20261225T203000" in text


def test_ics_folds_long_utf8_summary() -> None:
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="ы" * 80)
    lines = invite.ics_bytes.split(b"\r\n")
    folded = [line for line in lines if line.startswith(b" ")]

    assert any(line.startswith(b"SUMMARY:") for line in lines)
    assert folded
    for line in lines:
        assert len(line) <= 75


def test_ics_upload_uses_text_calendar_mime() -> None:
    from app.bot.telegram_session import document_upload_fields
    from app.services.meeting_invite import ICS_CONTENT_TYPE

    assert document_upload_fields("event.ics") == {
        "filename": "event.ics",
        "content_type": ICS_CONTENT_TYPE,
    }
    assert document_upload_fields("cover.jpg") == {"filename": "cover.jpg"}


def test_empty_public_url_has_no_inline_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "PUBLIC_BASE_URL", None)
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    assert invite.ics_url is None


def test_public_ics_url_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "PUBLIC_BASE_URL", "https://cal.example")
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")

    assert invite.ics_url is not None
    assert invite.ics_url.startswith("https://cal.example/invite/")
    assert invite.ics_url.endswith(".ics")

    from app.services.meeting_invite import invite_from_token

    token = invite.ics_url.rsplit("/", 1)[-1].removesuffix(".ics")
    restored = invite_from_token(token)
    assert restored is not None
    assert restored.title == invite.title
    assert restored.start == invite.start
    assert "DTSTART;TZID=Europe/Madrid:20260924T190000" in restored.ics_bytes.decode("utf-8")


async def test_ics_http_serves_text_calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "PUBLIC_BASE_URL", "https://cal.example")
    start = datetime(2026, 9, 24, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    assert invite.ics_url is not None
    token = invite.ics_url.rsplit("/", 1)[-1].removesuffix(".ics")

    from aiohttp.test_utils import TestClient, TestServer

    from app.http.calendar import create_calendar_app
    from app.services.meeting_invite import ICS_CONTENT_TYPE

    app = create_calendar_app()
    async with TestClient(TestServer(app)) as client:
        response = await client.get(f"/invite/{token}.ics")
        assert response.status == 200
        assert response.headers["Content-Type"] == ICS_CONTENT_TYPE
        assert "event.ics" in response.headers["Content-Disposition"]
        body = await response.read()
        text = body.decode("utf-8")
        assert "BEGIN:VCALENDAR" in text
        assert "DTSTART;TZID=Europe/Madrid:20260924T190000" in text

        missing = await client.get("/invite/not-a-token.ics")
        assert missing.status == 404
