from pathlib import Path

polls = Path("/home/farida/projects/malaga_book_club_bot/app/bot/polls.py")
polls.write_text(
    '''from aiogram import Bot
from aiogram.types import InputPollOption

from app.db.models import Book, SuggestionCycle
from app.services.cycle_service import format_poll_option, poll_intro_text, poll_question


async def publish_vote_polls(
    bot: Bot,
    chat_id: int,
    cycle: SuggestionCycle,
    chunks: list[list[Book]],
) -> None:
    await bot.send_message(chat_id, poll_intro_text())
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        used: set[str] = set()
        options: list[InputPollOption | str] = [format_poll_option(book, used) for book in chunk]
        await bot.send_poll(
            chat_id=chat_id,
            question=poll_question(cycle.target_month, index, total),
            options=options,
            is_anonymous=False,
            allows_multiple_answers=True,
            allow_adding_options=True,
        )
'''
)

cycle = Path("/home/farida/projects/malaga_book_club_bot/app/services/cycle_service.py")
text = cycle.read_text()
old = '''def poll_intro_text() -> str:
    return (
        "Голосуем за книгу месяца. Опросы неанонимные. "
        "Если опросов несколько, можно проголосовать в каждом."
    )
'''
new = '''def poll_intro_text() -> str:
    return (
        "Голосуем за книгу месяца. Можно выбрать несколько вариантов "
        "и добавить свой, если книги нет в списке. "
        "Опросы неанонимные. Если опросов несколько, можно проголосовать в каждом."
    )
'''
if old not in text:
    raise SystemExit("poll_intro_text block not found")
cycle.write_text(text.replace(old, new, 1))
print("updated")
