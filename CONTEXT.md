# Context & System Prompt: Telegram Bot for Malaga Book Club

## 1. Project Overview
We are building a production-ready asynchronous Telegram Bot for a local Book Club in Malaga.
The project serves as a Senior-level backend portfolio demonstrating Clean Architecture, Async-first design, strict typing, database migrations, and containerized infrastructure.

The bot lives in the club Telegram group and in private chat: on a scheduled day it opens book suggestions for the **next** month, members propose titles via `/suggest` (group topic and/or DM), and later the bot publishes non-anonymous Telegram polls (split into batches of 10 options).

## 2. Tech Stack & Environment
- **Language:** Python 3.12+ (Strict typing with `mypy`, linting with `ruff`)
- **Bot Framework:** `aiogram 3.x` (Routers, FSM, Middlewares, Inline Keyboards)
- **Database & ORM:** PostgreSQL 16 + `SQLAlchemy 2.0` (Async mode with `asyncpg`)
- **Migrations:** `Alembic` (Async mode)
- **Settings & Validation:** `Pydantic v2` + `pydantic-settings`
- **HTTP Client:** `httpx` (for external APIs like Google Books)
- **Scheduler:** APScheduler (`AsyncIOScheduler`, timezone `Europe/Madrid`)
- **Infrastructure:** Docker Compose (PostgreSQL 16 & Redis 7), running on Windows (PowerShell / WSL2)

## 3. Project Architecture & File Map
The project follows a layered architecture (Handlers -> Services -> Repositories -> Models):

book_club_bot/
├── app/
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── base.py          # /start and /start suggest deep link
│   │   │   ├── books.py         # /suggest FSM in group topic or private chat
│   │   │   ├── club_setup.py    # Group/topic bind, start polls, cycle status
│   │   │   ├── cycle_open.py    # Open/reopen suggestion cycle
│   │   │   └── admin.py         # Schedule days (overridden handlers in club_setup)
│   │   ├── club_chat.py         # Membership and suggest-access checks
│   │   ├── club_publish.py      # Announce + polls to group/topic
│   │   ├── keyboards/
│   │   │   ├── book.py          # Inline keyboard for search results
│   │   │   └── suggest.py       # Deep-link button to suggest in DM
│   │   └── polls.py             # Legacy sendPoll helper (club_publish is used)
│   ├── core/
│   │   ├── config.py            # Settings (incl. ADMIN_IDS, TIMEZONE, GROUP_CHAT_ID)
│   │   └── db.py                # Async engine, AsyncSessionLocal, get_async_session
│   ├── db/
│   │   └── models.py            # ORM models
│   ├── repositories/
│   │   ├── user_repo.py
│   │   ├── book_repo.py
│   │   ├── settings_repo.py
│   │   ├── cycle_repo.py
│   │   └── suggestion_repo.py
│   ├── services/
│   │   ├── google_books.py      # GoogleBooksService (httpx async requests)
│   │   ├── cycle_service.py     # Announcement, stack, poll chunking, captions
│   │   ├── club_destination.py  # Bound group + optional forum topic
│   │   └── club_scheduler.py    # Hourly cron for suggest_day / vote_day
│   └── schemas/
│       └── book.py              # BookSchema (incl. page_count)
├── alembic/                      # Async alembic migration scripts
├── docker-compose.yml            # Postgres (5432) & Redis (6379)
├── .env                          # Local secrets (BOT_TOKEN, DB credentials, ADMIN_IDS)
├── pyproject.toml                # Ruff and Mypy strict configuration
└── main.py                       # Polling + FSM MemoryStorage + scheduler

## 4. Current Progress & Status
1. **Infrastructure:** Docker containers (`book_club_db`, `book_club_redis`) are UP and RUNNING.
2. **Database:** Alembic migrations: `Initial tables` + `suggestion_cycles` + `suggest_topic_id`.
3. **ORM Models Defined (`app/db/models.py`):**
   - `User` (id=BigInteger telegram_id, username, full_name, role)
   - `Book` (id, title, authors, description, cover_url, google_id, page_count)
   - `ClubSettings` (group_chat_id, suggest_topic_id, suggest_day, vote_day, announce_hour)
   - `SuggestionCycle` (target_year, target_month, status SUGGESTING|VOTING|CLOSED)
   - `Suggestion` (cycle_id, book_id, user_id; unique per cycle+book)
   - `Meeting`, `Vote`, `RSVP` — leftover from earlier design, unused by the group cycle
4. **Current Features:**
   - `/start` registers/fetches the user via `UserRepository`. `/start suggest` opens the DM suggest flow.
   - Admin: `/set_group`, `/set_suggest_topic`, `/set_suggest_day`, `/set_vote_day`, `/open_suggestions`, `/start_vote`, `/cycle_status`.
   - Members (while status is SUGGESTING): `/suggest [title]` in the bound group (or its suggest topic) **or** in a private chat if they are still a group member → Google Books → inline select → card. From DM the card is also published to the group/topic.
   - Polls: native Telegram polls, `is_anonymous=False`, max 10 options; remainder of 1 is split as 9+2. Published to the bound topic when set.
   - Scheduler: hourly job; on `suggest_day` at/after `announce_hour` opens next month; on `vote_day` publishes polls.

## 5. Coding Standards & Guidelines for Cursor
- **SQLAlchemy 2.0 Syntax ONLY:** Use `Mapped[...]`, `mapped_column(...)`, `select(...)`. NEVER use legacy SQLAlchemy 1.x query syntax (`session.query()`).
- **Async First:** Always use `async`/`await` for DB sessions and HTTP calls (`AsyncSession`, `httpx.AsyncClient`).
- **Aiogram 3 Patterns:** Use Routers, FSM states (`StatesGroup`, `State`), and `CallbackData` classes for inline button handlers.
- **Type Safety:** Ensure strict typing across all functions, handlers, and repositories.
- **Clean Layers:** Keep handlers lightweight. Business logic goes into `Services`, DB operations go into `Repositories`.

## 6. Telegram setup
- Disable **Group Privacy Mode** in BotFather so `/suggest` can read the book title as a follow-up message.
- Add the bot as a **group admin** (required for non-anonymous polls and posting to forum topics).
- Put admin Telegram user ids in `ADMIN_IDS` (comma-separated).
- Members can `/suggest` in the group **or** in a private chat with the bot (must be a group member; `/start` in DM first).
- Optional forum topic: admin runs `/set_suggest_topic` inside the books topic; `/set_suggest_topic clear` unbinds it.

## 7. Immediate Next Goal
Optional later: close cycles, announce a winner, meetings/RSVP on top of the chosen book.
