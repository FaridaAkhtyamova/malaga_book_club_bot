from __future__ import annotations

import re
from dataclasses import dataclass

HASHTAG = "#выбор_книги"
_DESCRIPTION_LIMIT = 4000

_HASHTAG_RE = re.compile(r"#выбор_книги", re.IGNORECASE)
_PARSE_RE = re.compile(
    r"^(?P<title>.+?)[\s,;:–—\-]*"
    r"(?P<pages>\d{2,5})\s*(?:стр\.?|страниц[аыу]?)?\s*$",
    re.IGNORECASE,
)

GROUP_HINT = (
    f"В группе запостите карточку с тегом {HASHTAG}:\n"
    f"{HASHTAG} Название книги, 500\n"
    "Краткое описание книги\n\n"
    "Поиск по каталогу и добавление вручную — только в личке с ботом: /suggest"
)


@dataclass(frozen=True, slots=True)
class HashtagSuggestion:
    title: str
    page_count: int
    description: str | None = None


def parse_hashtag_suggestion(text: str) -> HashtagSuggestion | None:
    cleaned = _HASHTAG_RE.sub(" ", text, count=1).strip()
    first_line, _, rest = cleaned.partition("\n")
    match = _PARSE_RE.match(first_line.strip())
    if match is None:
        return None

    title = re.sub(r"\s+", " ", match.group("title")).strip(" \t,;—-")
    pages = int(match.group("pages"))
    if not title or pages < 1:
        return None

    description = rest.strip() or None
    if description is not None:
        description = description[:_DESCRIPTION_LIMIT]
    return HashtagSuggestion(title=title[:255], page_count=pages, description=description)
