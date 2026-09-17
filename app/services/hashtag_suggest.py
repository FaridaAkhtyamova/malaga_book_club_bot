from __future__ import annotations

import re
from dataclasses import dataclass

HASHTAG = "#выбор_книги"
_DESCRIPTION_LIMIT = 4000

_HASHTAG_RE = re.compile(r"#выбор_книги", re.IGNORECASE)
_PAGES_RE = re.compile(
    r"(?:"
    r"объём\s+страниц\s*[:\-]?\s*(\d{1,5})"
    r"|"
    r"(\d{1,5})\s*(?:страниц[аыуе]?|стр\.?)"
    r"|"
    r"(?:страниц[аыуе]?|стр\.?)\s*[:\-]?\s*(\d{1,5})"
    r")",
    re.IGNORECASE,
)
_PAGES_MISSING_RE = re.compile(r"^объём страниц не указан$", re.IGNORECASE)
_AUTHOR_MISSING_RE = re.compile(r"^автор не указан$", re.IGNORECASE)
_PROPOSED_RE = re.compile(r"^предложил", re.IGNORECASE)

CARD_TEMPLATE = (
    f"📖 {HASHTAG}\n"
    "Название книги\n"
    "Автор\n"
    "500 стр.\n"
    "\n"
    "Краткое описание книги"
)

GROUP_HINT = (
    f"📖 В группе запостите карточку:\n"
    f"{CARD_TEMPLATE}\n\n"
    "После тега — название, затем автор. "
    "Число страниц бот найдёт в любой строке со словами «стр» / «страниц». "
    "Кто предложил — из вашего сообщения.\n"
    "Обложку можно прикрепить картинкой.\n"
    "Поиск по каталогу и добавление вручную — только в личке с ботом: /suggest"
)


@dataclass(frozen=True, slots=True)
class HashtagSuggestion:
    title: str | None = None
    authors: str | None = None
    page_count: int | None = None
    description: str | None = None


def has_suggest_hashtag(text: str | None) -> bool:
    if not text:
        return False
    return _HASHTAG_RE.search(_plain_hashtag_text(text)) is not None


def suggest_source_text(*parts: str | None) -> str | None:
    for part in parts:
        if has_suggest_hashtag(part):
            return _plain_hashtag_text(part)
    return None


def _plain_hashtag_text(text: str) -> str:
    return text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")


def parse_hashtag_suggestion(text: str) -> HashtagSuggestion | None:
    if not _HASHTAG_RE.search(text):
        return None

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _HASHTAG_RE.search(line):
            continue
        leftover = _HASHTAG_RE.sub(" ", line, count=1)
        leftover = re.sub(r"[📖]", " ", leftover)
        leftover = leftover.strip()
        rest = lines[index + 1 :]
        if leftover:
            return _parse_same_line(leftover, rest)
        return _parse_body(rest)
    return HashtagSuggestion()


def _parse_same_line(first_line: str, rest: list[str]) -> HashtagSuggestion:
    parsed = _parse_body([first_line, *rest])
    title = parsed.title
    description_parts: list[str] = []
    if parsed.authors:
        description_parts.append(parsed.authors)
    if parsed.description:
        description_parts.append(parsed.description)
    return HashtagSuggestion(
        title=title,
        authors=None,
        page_count=parsed.page_count,
        description=_join_description(description_parts),
    )


def _parse_body(lines: list[str]) -> HashtagSuggestion:
    page_count: int | None = None
    kept: list[str] = []
    for raw in lines:
        line = _normalize_line(raw)
        if not line:
            continue
        if _PROPOSED_RE.match(line):
            continue
        if _PAGES_MISSING_RE.match(line):
            continue
        pages = _pages_from_text(line)
        if pages is not None and page_count is None:
            page_count = pages
            remainder = _strip_pages(line)
            if remainder:
                kept.append(remainder)
            continue
        kept.append(line)

    if not kept:
        return HashtagSuggestion(page_count=page_count)

    title = kept[0][:255]
    authors: str | None = None
    body: list[str] = []
    if len(kept) >= 2:
        second = kept[1]
        if not _AUTHOR_MISSING_RE.match(second):
            authors = second[:500]
        body = kept[2:]

    return HashtagSuggestion(
        title=title,
        authors=authors,
        page_count=page_count,
        description=_join_description(body),
    )


def _pages_from_text(text: str) -> int | None:
    match = _PAGES_RE.search(text)
    if match is None:
        return None
    for group in match.groups():
        if group is None:
            continue
        pages = int(group)
        if pages >= 1:
            return pages
    return None


def _strip_pages(line: str) -> str:
    stripped = _PAGES_RE.sub(" ", line, count=1)
    stripped = re.sub(r"[\s,;:–—\-]+", " ", stripped).strip(" \t,;—-")
    return stripped


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _join_description(lines: list[str]) -> str | None:
    description = "\n".join(line.strip() for line in lines).strip() or None
    if description is not None:
        return description[:_DESCRIPTION_LIMIT]
    return None
