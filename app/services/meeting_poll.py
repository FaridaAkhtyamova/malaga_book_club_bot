from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

STUB_SELECTED_BOOK_TITLE = "Книга месяца (заглушка)"
DATE_OPTION_COUNT = 10
DATE_OFFSET_DAYS = 2
OPTION_UNREAD = "не прочитала"
OPTION_SKIP = "пропущу"

WEEKDAYS_RU: tuple[str, ...] = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def get_selected_book_title() -> str:
    """Placeholder until the previous vote winner is stored."""
    return STUB_SELECTED_BOOK_TITLE


def meeting_poll_question(title: str) -> str:
    return f"Когда встречаемся по «{title}»?"


def meeting_poll_intro(title: str) -> str:
    return (
        f"Голосуем за дату встречи по «{title}». "
        "Можно выбрать несколько дней, отметить «не прочитала» или «пропущу», "
        "и добавить свой вариант. Опрос неанонимный."
    )


def meeting_poll_options(now: datetime | None = None) -> list[str]:
    start = _localized_today(now) + timedelta(days=DATE_OFFSET_DAYS)
    dates = [
        _format_date_option(start + timedelta(days=offset)) for offset in range(DATE_OPTION_COUNT)
    ]
    return [*dates, OPTION_UNREAD, OPTION_SKIP]


def _localized_today(now: datetime | None) -> date:
    tz = ZoneInfo(get_settings().TIMEZONE)
    if now is None:
        current = datetime.now(tz)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=tz)
    else:
        current = now.astimezone(tz)
    return current.date()


def _format_date_option(day: date) -> str:
    return f"{day.day}, {WEEKDAYS_RU[day.weekday()]}"
