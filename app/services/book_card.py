import html
import re

from app.db.models import Book, User
from app.services.cycle_service import format_book_card as _format_book_card
from app.services.hashtag_suggest import HASHTAG

_PAGES_LINE = re.compile(r"^(\d+) стр\.$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
PHOTO_CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


def format_book_card(book: Book, suggester: User) -> str:
    text = _format_book_card(book, suggester)
    text = text.replace("объём не указан", "объём страниц не указан")
    return _PAGES_LINE.sub(r"объём страниц: \1", text, count=1)


def format_group_card(book: Book, suggester: User) -> str:
    title = html.escape(book.title)
    authors = html.escape(book.authors or "автор не указан")
    pages = (
        f"объём страниц: {book.page_count}" if book.page_count else "объём страниц не указан"
    )
    who = _suggester_label(suggester)
    header = (
        f"{HASHTAG}\n<b>{title}</b>\n{authors}\n{html.escape(pages)}\nПредложил(а): {who}"
    )
    description = _HTML_TAG_RE.sub("", book.description or "").strip()
    if not description:
        return header

    separator = "\n\n"
    remaining = MESSAGE_LIMIT - len(header) - len(separator)
    fitted = _fit_html_text(description, remaining)
    if not fitted:
        return header
    return f"{header}{separator}{fitted}"


def _suggester_label(suggester: User) -> str:
    if suggester.username:
        return f"@{html.escape(suggester.username)}"
    return html.escape(suggester.full_name or str(suggester.id))


def _fit_html_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    escaped = html.escape(text)
    if len(escaped) <= limit:
        return escaped
    if limit <= 1:
        return "…"[:limit]
    cut = min(len(text), limit)
    while cut > 0:
        candidate = html.escape(text[:cut]) + "…"
        if len(candidate) <= limit:
            return candidate
        cut -= 1
    return ""
