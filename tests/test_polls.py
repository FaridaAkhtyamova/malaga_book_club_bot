from datetime import UTC, date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.db.models import Book
from app.services.cycle_service import chunk_books_for_polls, collection_month_start, naive_utc
from app.services.meeting_poll import (
    HourVoteCounts,
    format_meeting_hour,
    meeting_time_announcement,
    meeting_time_poll_options,
    merge_hour_counts,
    tally_meeting_hours,
)
from app.services.vote_close import VoteCounts


def _book(book_id: int) -> Book:
    return Book(
        id=book_id,
        title=f"Book {book_id}",
        google_id=f"g-{book_id}",
    )


def test_chunk_avoids_single_option_remainder() -> None:
    books = [_book(i) for i in range(11)]
    chunks = chunk_books_for_polls(books)
    assert [len(chunk) for chunk in chunks] == [9, 2]


def test_chunk_requires_at_least_two_books() -> None:
    assert chunk_books_for_polls([_book(1)]) == []


def test_vote_counts_detect_tie() -> None:
    tallies = VoteCounts(by_book={1: 4, 2: 4, 3: 1})
    assert tallies.total == 9
    assert tallies.leaders() == [1, 2]


def test_vote_counts_single_winner() -> None:
    tallies = VoteCounts(by_book={1: 2, 2: 5})
    assert tallies.leaders() == [2]


def test_collection_month_start_uses_first_of_opened_month() -> None:
    opened = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    start = collection_month_start(opened, ZoneInfo("Europe/Madrid"))
    assert start == datetime(2026, 9, 1, tzinfo=ZoneInfo("Europe/Madrid"))
    assert naive_utc(start) == datetime(2026, 8, 31, 22, 0)


def test_meeting_time_options_are_hourly_from_10_to_19() -> None:
    choices = meeting_time_poll_options()
    hours = [choice.hour for choice in choices]
    assert hours == list(range(10, 20))
    assert [choice.label for choice in choices] == [format_meeting_hour(hour) for hour in hours]


def test_tally_meeting_hours_detect_tie() -> None:
    tallies = tally_meeting_hours(
        [10, 11, 12],
        [
            SimpleNamespace(voter_count=4),
            SimpleNamespace(voter_count=4),
            SimpleNamespace(voter_count=1),
        ],
    )
    assert tallies.total == 9
    assert tallies.leaders() == [10, 11]


def test_tally_meeting_hours_single_winner() -> None:
    tallies = tally_meeting_hours(
        [18, 19],
        [
            SimpleNamespace(voter_count=2),
            SimpleNamespace(voter_count=5),
        ],
    )
    assert tallies.leaders() == [19]


def test_merge_hour_counts_adds_votes() -> None:
    merged = merge_hour_counts(
        [
            HourVoteCounts(by_hour={10: 1, 11: 2}),
            HourVoteCounts(by_hour={11: 3, 12: 1}),
        ]
    )
    assert merged.by_hour == {10: 1, 11: 5, 12: 1}
    assert merged.leaders() == [11]


def test_meeting_time_announcement_includes_date_and_hour() -> None:
    cycle = SimpleNamespace(target_month=10)
    book = _book(1)
    book.title = "Dune"
    text = meeting_time_announcement(cycle, book, date(2026, 10, 25), 19)
    assert "Dune" in text
    assert "19:00" in text
    assert "25 октября" in text
