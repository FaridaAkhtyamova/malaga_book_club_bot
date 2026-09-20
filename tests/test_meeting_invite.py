from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.config import get_settings
from app.services.meeting_invite import build_meeting_invite, event_title


@pytest.fixture(autouse=True)
def madrid_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "TIMEZONE", "Europe/Madrid")


def test_ics_uses_utc_and_omits_publish_method() -> None:
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    text = invite.ics_bytes.decode("utf-8")

    assert "METHOD:" not in text
    assert "BEGIN:VTIMEZONE" not in text
    assert "DTSTART:20260925T170000Z" in text
    assert "DTEND:20260925T183000Z" in text
    assert "SEQUENCE:0" in text
    assert text.endswith("\r\n")
    assert "\r\nBEGIN:VEVENT\r\n" in text


def test_ics_converts_winter_madrid_time_to_utc() -> None:
    start = datetime(2026, 12, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    text = invite.ics_bytes.decode("utf-8")

    assert "DTSTART:20261225T180000Z" in text
    assert "DTEND:20261225T193000Z" in text


def test_ics_folds_long_utf8_summary() -> None:
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="ы" * 80)
    lines = invite.ics_bytes.split(b"\r\n")
    folded = [line for line in lines if line.startswith(b" ")]

    assert any(line.startswith(b"SUMMARY:") for line in lines)
    assert folded
    for line in lines:
        assert len(line) <= 75


def test_calendar_links_use_malaga_local_time() -> None:
    start = datetime(2026, 9, 25, 19, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    invite = build_meeting_invite(start, book_title="Dune")
    title = event_title("Dune")

    assert invite.title == title
    assert "calendar.google.com/calendar/render" in invite.google_url
    assert "20260925T190000" in invite.google_url
    assert "20260925T203000" in invite.google_url
    assert "ctz=Europe%2FMadrid" in invite.google_url
    assert "outlook.live.com/calendar" in invite.outlook_url
    assert "startdt=2026-09-25T17%3A00%3A00Z" in invite.outlook_url
    assert "enddt=2026-09-25T18%3A30%3A00Z" in invite.outlook_url
