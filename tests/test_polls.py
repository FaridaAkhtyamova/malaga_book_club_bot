from app.db.models import Book
from app.services.cycle_service import chunk_books_for_polls
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
