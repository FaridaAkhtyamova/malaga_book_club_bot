# Context: Telegram Bot for Malaga Book Club

## 1. Project Overview
Async Telegram bot for a local book club in Malaga. Portfolio piece: layered architecture, async-first Python, Alembic, Docker.

The bot lives in the club group and in private chat. It posts announcements, polls, book cards, and calendar invites to the group, but does not reply there. Conversation (commands, `/suggest`, admin flow) is DM-only, except one-time `/set_group` and `/set_suggest_topic` which must be invoked in the group. One bot instance can serve several groups: each bound chat is its own club with separate settings and suggestion cycles. On a scheduled (or admin) day it opens book suggestions for the **next** month. Members propose titles via `#выбор_книги` in the group or `/suggest` in DM. Later the bot publishes non-anonymous Telegram polls, can run a runoff on a tie, then a meeting-date poll and a calendar invite (`.ics`).

## 2. Tech Stack
- **Language:** Python 3.12+ (`mypy` strict, `ruff`)
- **Bot:** aiogram 3.x (routers, FSM `MemoryStorage`, middlewares, inline keyboards)
- **DB:** PostgreSQL 16, SQLAlchemy 2.0 + `asyncpg`, Alembic (async)
- **Settings:** Pydantic v2 + `pydantic-settings`
- **HTTP:** `httpx` (Google Books, Open Library)
- **Scheduler:** APScheduler (`AsyncIOScheduler`, timezone `Europe/Madrid`)
- **Infra:** Docker Compose — Postgres `5432` + bot image (`book_club_db`, `book_club_bot`)

## 3. Architecture
Handlers → Services → Repositories → Models

```
book_club_bot/
├── app/
│   ├── bot/
│   │   ├── handlers/     # base, books, clubs, group_suggest, group_card_review, club_setup, cycle_open, meeting, admin
│   │   ├── club_chat.py  # membership, club-admin, and suggest-access checks
│   │   ├── club_context.py  # pick active club in DM when several groups are bound
│   │   ├── admin_filter.py
│   │   ├── club_publish.py
│   │   ├── commands.py   # BotFather menu + /help
│   │   ├── keyboards/
│   │   └── middlewares/  # DbSessionMiddleware
│   ├── core/             # Settings, async engine
│   ├── db/models.py
│   ├── repositories/
│   ├── services/         # catalog, cycle, destination, scheduler, meeting invite
│   └── schemas/
├── alembic/versions/
├── docker-compose.yml
├── tests/
├── main.py
└── README.md             # operator-facing how-to (Russian)
```

## 4. ORM (`app/db/models.py`)
- `User` — telegram id PK, username, full_name, optional `active_club_id` (last club used in DM), `role` (unused; admins are group administrators of a bound club chat)
- `Book` — catalog + manual (`google_id` unique; manuals use `manual-<uuid>`)
- `ClubSettings` — one row per bound group: group, optional title and forum topic, suggest/vote days, announce hour
- `SuggestionCycle` — per club + target month, SUGGESTING|VOTING|CLOSED, optional winner book and meeting date
- `Suggestion` — unique per cycle+book
- `PendingGroupCard` — group `#выбор_книги` posts waiting for admin review before the book poll
- `VotePoll` / `MeetingPoll` — Telegram poll message ids and option mapping
- `Meeting`, `Vote`, `RSVP` — leftover from an earlier design; not used by the current cycle

## 5. Features (current)
- `/start` is DM-only: registers the user and explains how to suggest; `/start suggest` opens the DM suggest flow; `/help` lists commands; `/clubs` lists/switches clubs. Commands other than `/set_group` and `/set_suggest_topic` are ignored in the group
- Group: `#выбор_книги` card (title, author; pages from «стр»/«страниц»; suggester from Telegram user); stored silently for admin review, then included in `/start_vote`. The bot does not reply to the card in the group
- DM: `/suggest` → Google Books (`intitle` / `printType=books`, then full-text if thin), then Open Library; results are deduped and ranked by title/author match; manual add; confirm before posting the card to the group/topic
- Admin: `/set_group`, `/set_suggest_topic`, `/clubs`, `/set_suggest_day`, `/set_vote_day`, `/open_suggestions`, `/start_vote`, `/close_vote`, `/reset_vote`, `/start_meeting_poll`, `/close_meeting_poll`, `/create_meeting`, `/cycle_status`, `/month_book`
- `/close_vote` with a single winner also publishes the meeting-date poll; `/start_meeting_poll` works without a closed book vote and asks the admin for a title if none is stored
- `/reset_vote` stops book and meeting polls without picking a winner and republishes book polls with suggestions from the 1st of the cycle's collection month
- `/close_meeting_poll` with a single date publishes the date in the group (no admin command in that message) and DMs admins to run `/create_meeting`
- `/create_meeting` uses the poll-chosen meeting date when it exists; otherwise the admin types the date (`25.09` / `25.09.2026`). If there is no winner book, the admin types the title before the time
- Polls: `is_anonymous=False`; max 10 options; remainder of 1 is split as 9+2; first round allows multiple answers
- Scheduler (hourly): for each bound club, on `suggest_day` at/after `announce_hour` opens next month; on `vote_day` publishes book polls unless unread group cards are waiting for admin review. Closing polls is always manual
- `DEBUG=true` lets `/open_suggestions` reset the current month for local testing

## 6. Telegram setup
- Disable **Group Privacy Mode** in BotFather so the bot sees `#выбор_книги`
- Bot must be a **group admin** (non-anonymous polls, forum topics)
- Club admins are Telegram administrators of each bound group (not a list in `.env`)
- Optional forum topic per club: `/set_suggest_topic` inside the books topic; `/set_suggest_topic clear` unbinds it
- DM commands use the user's active club; if they belong to several, the bot asks them to pick (`/clubs`)

## 7. Coding standards
- SQLAlchemy 2.0 only: `Mapped[...]`, `mapped_column(...)`, `select(...)`. Never `session.query()`
- Async first: `AsyncSession`, `httpx.AsyncClient`
- Aiogram 3: routers, FSM, `CallbackData`
- Strict typing; handlers stay thin
