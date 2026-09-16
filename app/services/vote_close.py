from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from aiogram.types import PollOption

from app.db.models import Book, SuggestionCycle
from app.services.cycle_service import month_name_ru


@dataclass(frozen=True, slots=True)
class VoteCounts:
    by_book: dict[int, int]

    @property
    def total(self) -> int:
        return sum(self.by_book.values())

    def leaders(self) -> list[int]:
        if not self.by_book:
            return []
        top = max(self.by_book.values())
        return [book_id for book_id, votes in self.by_book.items() if votes == top]


def add_poll_votes(
    counts: dict[int, int],
    option_book_ids: Sequence[int],
    options: Sequence[PollOption],
) -> None:
    for index, book_id in enumerate(option_book_ids):
        if index >= len(options):
            break
        counts[book_id] = counts.get(book_id, 0) + options[index].voter_count


def winner_announcement(cycle: SuggestionCycle, book: Book) -> str:
    month = month_name_ru(cycle.target_month)
    authors = book.authors or "автор не указан"
    return f"🏆 Книга на {month}: «{book.title}»\n{authors}"


def runoff_intro_text() -> str:
    return (
        "🔁 Ничья. Голосуем ещё раз — только книги с одинаковым числом голосов. "
        "Опрос неанонимный, один вариант."
    )


def runoff_question(month: int) -> str:
    return f"🗳️ Книга на {month_name_ru(month)} — второй тур"
