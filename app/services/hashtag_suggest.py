from __future__ import annotations

import re
from dataclasses import dataclass

HASHTAG = "#выбор_книги"
_DESCRIPTION_LIMIT = 4000

_HASHTAG_RE = re.compile(r"#выбор_книги", re.IGNORECASE)
_COMPACT_RE = re.compile(
    r"^(?P<title>.+?)(?:[\s,;:–—\-]+"
    r"(?P<pages>\d{2,5})\s*(?:стр\.?|страниц[аыу]?)?)?\s*$",
    re.IGNORECASE,
)
_PAGES_LINE_RE = re.compile(
    r"^(?:объём страниц:\s*)?(?P<pages>\d{2,5})\s*(?:стр\.?|страниц[аыу]?)?\s*$",
    re.IGNORECASE,
)
_PAGES_MISSING_RE = re.compile(r"^объём страниц не указан$", re.IGNORECASE)
_AUTHOR_MISSING_RE = re.compile(r"^автор не указан$", re.IGNORECASE)
_PROPOSED_RE = re.compile(r"^предложил", re.IGNORECASE)

GROUP_HINT = (
    f"📖 В группе запостите карточку с тегом {HASHTAG}. "
    "Перед голосованием её проверит админ.\n"
    f"{HASHTAG} Название книги, 500\n"
    "Краткое описание книги\n\n"
    "Поиск по каталогу и добавление вручную — только в личке с ботом: /suggest"
)


@dataclass(frozen=True, slots=True)
class HashtagSuggestion:
    title: str | None = None
    authors: str | None = None
    page_count: int | None = None
    description: str | None = None


def parse_hashtag_suggestion(text: str) -> HashtagSuggestion | None:
    if not _HASHTAG_RE.search(text):
        return None

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _HASHTAG_RE.search(line):
            continue
        leftover = _HASHTAG_RE.sub(" ", line, count=1)
        leftover = re.sub(r"[📖]", " ", leftover)
        leftover = re.sub(r"\s+", " ", leftover).strip(" \t,;—-")
        rest = lines[index + 1 :]
        if leftover:
            return _parse_compact(leftover, rest)
        return _parse_card(rest)
    return HashtagSuggestion()


def _parse_compact(first_line: str, rest: list[str]) -> HashtagSuggestion:
    match = _COMPACT_RE.match(first_line)
    title: str | None = None
    page_count: int | None = None
    if match is not None:
        title = re.sub(r"\s+", " ", match.group("title")).strip(" \t,;—-") or None
        raw_pages = match.group("pages")
        if raw_pages is not None:
            pages = int(raw_pages)
            page_count = pages if pages >= 1 else None
    elif first_line:
        title = first_line[:255]

    description = _join_description(rest)
    return HashtagSuggestion(
        title=title[:255] if title else None,
        page_count=page_count,
        description=description,
    )


def _parse_card(lines: list[str]) -> HashtagSuggestion:
    cleaned = [_normalize_line(line) for line in lines]
    cleaned = [line for line in cleaned if line]
    if not cleaned:
        return HashtagSuggestion()

    title = cleaned[0][:255]
    page_count: int | None = None
    authors: str | None = None
    authors_consumed = False
    body: list[str] = []
    for line in cleaned[1:]:
        if _PROPOSED_RE.match(line):
            continue
        if _PAGES_MISSING_RE.match(line):
            continue
        pages = _pages_from_line(line)
        if pages is not None and page_count is None:
            page_count = pages
            continue
        if not authors_consumed and not body:
            authors_consumed = True
            if not _AUTHOR_MISSING_RE.match(line):
                authors = line[:500]
            continue
        body.append(line)

    return HashtagSuggestion(
        title=title,
        authors=authors,
        page_count=page_count,
        description=_join_description(body),
    )


def _pages_from_line(line: str) -> int | None:
    match = _PAGES_LINE_RE.match(line)
    if match is None:
        return None
    pages = int(match.group("pages"))
    return pages if pages >= 1 else None


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _join_description(lines: list[str]) -> str | None:
    description = "\n".join(line.strip() for line in lines).strip() or None
    if description is not None:
        return description[:_DESCRIPTION_LIMIT]
    return None
