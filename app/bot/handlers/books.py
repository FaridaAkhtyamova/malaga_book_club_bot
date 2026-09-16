from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.book import (
    BookConfirmCallback,
    BookMissingCallback,
    BookNavCallback,
    BookSelectCallback,
)
from app.bot.club_chat import SuggestAccess, resolve_suggest_access, send_html_card
from app.bot.keyboards.book import (
    CANCEL_BUTTON,
    RETRY_BUTTON,
    confirm_send_keyboard,
    search_results_keyboard,
    suggest_control_keyboard,
)
from app.bot.states.book import BookSearchStates
from app.db.models import Book, User
from app.repositories.user_repo import UserRepository
from app.schemas.book import BookSchema
from app.services.book_card import format_book_card, format_group_card
from app.services.catalog import search_catalog
from app.services.club_destination import DestinationService
from app.services.cycle_service import CycleNotOpenError, CycleService
from app.services.hashtag_suggest import GROUP_HINT
from app.services.manual_book import ManualBookService

logger = logging.getLogger(__name__)
router = Router()

_SKIP = "-"
_KEEP_QUERY = "."
_SUGGEST_STATES = StateFilter(BookSearchStates)
_CANCELLED = "Отменено. Чтобы предложить книгу, снова отправьте /suggest."
_ENTER_TITLE = "Введите название книги."
_ENTER_COVER = "Прикрепите обложку картинкой. Если без обложки — отправьте `-`."


@router.message(Command("suggest"))
async def cmd_suggest(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    query = (command.args or "").strip() or None
    await begin_suggest(message, state, session, bot, query=query)


@router.message(Command("cancel"))
@router.message(_SUGGEST_STATES, F.text == CANCEL_BUTTON)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Сейчас нет активной операции.")
        return
    await _cancel_flow(message, state)


@router.message(_SUGGEST_STATES, F.text == RETRY_BUTTON)
async def cmd_retry_search(message: Message, state: FSMContext) -> None:
    await _restart_search(message, state)


@router.callback_query(BookNavCallback.filter(), _SUGGEST_STATES)
async def on_search_nav(
    callback: CallbackQuery,
    callback_data: BookNavCallback,
    state: FSMContext,
) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    if callback_data.action == "retry":
        await _restart_search(callback.message, state)
        return
    await _cancel_flow(callback.message, state)


@router.message(BookSearchStates.waiting_query, F.text)
async def process_search_query(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return

    query = (message.text or "").strip()
    if not query:
        await message.answer(_ENTER_TITLE)
        return

    await _search_and_show(message, state, query)


@router.callback_query(BookMissingCallback.filter(), _SUGGEST_STATES)
async def on_book_missing(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    if not await _ensure_can_suggest_callback(callback, session, bot, state):
        return

    data = await state.get_data()
    query = data.get("query")
    query_text = query.strip() if isinstance(query, str) else ""

    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(BookSearchStates.waiting_manual_title)
    await callback.answer()
    if query_text:
        await callback.message.answer(
            f"Введите название книги. Чтобы оставить «{query_text}», отправьте точку (`.`)."
        )
        return
    await callback.message.answer(_ENTER_TITLE)


@router.message(BookSearchStates.waiting_manual_title, F.text)
async def process_manual_title(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return

    data = await state.get_data()
    query = data.get("query")
    query_text = query.strip() if isinstance(query, str) else ""
    raw = (message.text or "").strip()
    title = query_text if raw == _KEEP_QUERY and query_text else raw
    if not title or title == _KEEP_QUERY:
        await message.answer(_ENTER_TITLE)
        return

    await state.update_data(manual_title=title)
    await state.set_state(BookSearchStates.waiting_manual_authors)
    await message.answer("Автор(ы). Если не знаете — отправьте `-`.")


@router.message(BookSearchStates.waiting_manual_authors, F.text)
async def process_manual_authors(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return

    raw = (message.text or "").strip()
    authors = None if raw == _SKIP else raw
    await state.update_data(manual_authors=authors)
    await state.set_state(BookSearchStates.waiting_manual_pages)
    await message.answer("Число страниц. Если не знаете — отправьте `-`.")


@router.message(BookSearchStates.waiting_manual_pages, F.text)
async def process_manual_pages(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return

    raw = (message.text or "").strip()
    page_count: int | None
    if raw == _SKIP:
        page_count = None
    elif raw.isdigit() and int(raw) > 0:
        page_count = int(raw)
    else:
        await message.answer("Введите целое число страниц или `-`.")
        return

    await state.update_data(manual_pages=page_count)
    await state.set_state(BookSearchStates.waiting_manual_description)
    await message.answer(
        "Введите описание книги, чтобы участники могли с ней ознакомиться. "
        "Если не нужно — отправьте `-`."
    )


@router.message(BookSearchStates.waiting_manual_description, F.text)
async def process_manual_description(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return

    raw = (message.text or "").strip()
    description = None if raw == _SKIP else raw[:4000]
    await state.update_data(manual_description=description)
    await state.set_state(BookSearchStates.waiting_manual_cover)
    await message.answer(_ENTER_COVER)


@router.message(BookSearchStates.waiting_manual_cover, F.photo)
@router.message(BookSearchStates.waiting_manual_cover, F.document)
@router.message(BookSearchStates.waiting_manual_cover, F.text)
async def process_manual_cover(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return
    if message.from_user is None:
        return

    cover_id = _cover_file_id(message)
    if cover_id is None:
        raw = (message.text or "").strip()
        if raw != _SKIP:
            await message.answer(_ENTER_COVER)
            return
    await _finish_manual_card(message, state, session, cover_id)


@router.callback_query(BookSelectCallback.filter(), _SUGGEST_STATES)
async def on_book_select(
    callback: CallbackQuery,
    callback_data: BookSelectCallback,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    if callback.from_user is None:
        await callback.answer()
        return

    if not await _ensure_can_suggest_callback(callback, session, bot, state):
        return

    data = await state.get_data()
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []

    raw_book = next(
        (
            item
            for item in results
            if isinstance(item, dict) and item.get("google_id") == callback_data.google_id
        ),
        None,
    )
    if raw_book is None:
        await callback.answer("Книга не найдена в результатах. Повторите поиск.", show_alert=True)
        return

    book_schema = BookSchema.model_validate(raw_book)
    await state.update_data(pending={"kind": "catalog", "book": book_schema.model_dump()})
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    preview = _preview_book(await state.get_data())
    if preview is None:
        await callback.answer("Не удалось подготовить карточку.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _ask_confirm(callback.message, state, preview, user)


@router.message(BookSearchStates.waiting_confirm, F.text)
async def process_confirm_text(message: Message) -> None:
    await message.answer(
        f"Подтвердите отправку кнопками выше, нажмите «{RETRY_BUTTON}» "
        f"или «{CANCEL_BUTTON}»."
    )


@router.callback_query(BookConfirmCallback.filter(), BookSearchStates.waiting_confirm)
async def on_confirm_send(
    callback: CallbackQuery,
    callback_data: BookConfirmCallback,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    if callback.from_user is None:
        await callback.answer()
        return
    if not await _ensure_can_suggest_callback(callback, session, bot, state):
        return

    if callback_data.action == "retry":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _restart_search(callback.message, state)
        return

    if callback_data.action != "ok":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await _cancel_flow(callback.message, state)
        return

    data = await state.get_data()
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    try:
        book, created = await _save_pending(session, user, data)
    except CycleNotOpenError as exc:
        await state.clear()
        await callback.answer(str(exc), show_alert=True)
        await callback.message.answer(_CANCELLED, reply_markup=ReplyKeyboardRemove())
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    if not created:
        await callback.answer()
        await callback.message.answer(
            "Эта книга уже предложена в этом цикле.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await callback.answer()
    published = await _publish_to_group(bot, session, book, user)
    text = (
        "Карточка отправлена в общий чат."
        if published
        else "Книга сохранена, но карточку в группу отправить не удалось."
    )
    await callback.message.answer(text, reply_markup=ReplyKeyboardRemove())


@router.callback_query(BookNavCallback.filter())
@router.callback_query(BookConfirmCallback.filter())
@router.callback_query(BookSelectCallback.filter())
@router.callback_query(BookMissingCallback.filter())
async def on_stale_book_callback(callback: CallbackQuery) -> None:
    await callback.answer("Операция уже завершена. Начните заново: /suggest", show_alert=True)


async def begin_suggest(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    *,
    query: str | None = None,
) -> None:
    if not await _ensure_can_suggest(message, session, bot, state):
        return

    if message.chat.type != ChatType.PRIVATE:
        await message.answer(GROUP_HINT)
        return

    await state.clear()
    if query:
        await message.answer("Ищу…", reply_markup=suggest_control_keyboard())
        await _search_and_show(message, state, query)
        return

    await state.set_state(BookSearchStates.waiting_query)
    await message.answer(_ENTER_TITLE, reply_markup=suggest_control_keyboard())


async def _ensure_can_suggest(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext | None = None,
) -> bool:
    if message.from_user is None:
        return False
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(GROUP_HINT)
        return False
    access = await _resolve_access(bot, session, message, message.from_user.id)
    if access.allowed:
        return True
    if state is not None and access.clear_state:
        await state.clear()
    if access.error:
        await message.answer(access.error, reply_markup=ReplyKeyboardRemove())
    return False


async def _ensure_can_suggest_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    state: FSMContext | None = None,
) -> bool:
    if callback.message is None or not isinstance(callback.message, Message):
        await callback.answer()
        return False
    if callback.from_user is None:
        await callback.answer()
        return False
    if callback.message.chat.type != ChatType.PRIVATE:
        await callback.answer("В группе используйте #выбор_книги", show_alert=True)
        return False
    access = await _resolve_access(bot, session, callback.message, callback.from_user.id)
    if access.allowed:
        return True
    if state is not None and access.clear_state:
        await state.clear()
    await callback.answer(access.callback_error or access.error or "Нельзя", show_alert=True)
    if access.clear_state:
        await callback.message.answer(
            "Операция остановлена.",
            reply_markup=ReplyKeyboardRemove(),
        )
    return False


async def _resolve_access(
    bot: Bot,
    session: AsyncSession,
    message: Message,
    user_id: int,
) -> SuggestAccess:
    return await resolve_suggest_access(
        bot,
        CycleService(session),
        chat_type=message.chat.type,
        chat_id=message.chat.id,
        user_id=user_id,
        thread_id=message.message_thread_id,
    )


def _actor_label(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "unknown"
    username = f"@{user.username}" if user.username else "-"
    name = user.full_name or "-"
    return f"{name} ({username}, id={user.id})"


async def _search_and_show(message: Message, state: FSMContext, query: str) -> None:
    await state.set_state(BookSearchStates.waiting_query)
    await state.update_data(query=query, results=[], pending=None)
    logger.info("Book search query=%r by %s", query, _actor_label(message))
    books = await search_catalog(query)
    logger.info(
        "Book search query=%r by %s returned %s result(s)",
        query,
        _actor_label(message),
        len(books),
    )
    await state.update_data(results=[book.model_dump() for book in books])
    if not books:
        await message.answer(
            "Ничего не найдено. Добавьте книгу вручную, отправьте другой запрос "
            f"или нажмите «{RETRY_BUTTON}».",
            reply_markup=search_results_keyboard([]),
        )
        return

    await message.answer(
        "Выберите книгу или отправьте другой запрос.",
        reply_markup=search_results_keyboard(books),
    )


async def _cancel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_CANCELLED, reply_markup=ReplyKeyboardRemove())


async def _restart_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookSearchStates.waiting_query)
    await message.answer(_ENTER_TITLE, reply_markup=suggest_control_keyboard())


async def _ask_confirm(message: Message, state: FSMContext, book: Book, user: User) -> None:
    await state.set_state(BookSearchStates.waiting_confirm)
    caption = format_book_card(book, user)
    await _send_book_card(message, book.cover_url, caption)
    await message.answer(
        "Отправить эту карточку в общий чат?",
        reply_markup=confirm_send_keyboard(),
    )


def _preview_book(data: dict[str, object]) -> Book | None:
    pending = data.get("pending")
    if not isinstance(pending, dict):
        return None
    kind = pending.get("kind")
    if kind == "catalog":
        raw = pending.get("book")
        if not isinstance(raw, dict):
            return None
        schema = BookSchema.model_validate(raw)
        authors = ", ".join(schema.authors) if schema.authors else None
        return Book(
            title=schema.title[:255],
            authors=authors,
            description=schema.description,
            cover_url=schema.cover_url,
            google_id=schema.google_id,
            page_count=schema.page_count,
        )
    if kind == "manual":
        title = pending.get("title")
        if not isinstance(title, str) or not title:
            return None
        authors = pending.get("authors")
        description = pending.get("description")
        pages = pending.get("page_count")
        cover_url = pending.get("cover_url")
        return Book(
            title=title[:255],
            authors=authors if isinstance(authors, str) else None,
            description=description if isinstance(description, str) else None,
            cover_url=cover_url if isinstance(cover_url, str) else None,
            google_id="preview",
            page_count=pages if isinstance(pages, int) else None,
        )
    return None


async def _save_pending(
    session: AsyncSession,
    user: User,
    data: dict[str, object],
) -> tuple[Book, bool]:
    pending = data.get("pending")
    if not isinstance(pending, dict):
        raise CycleNotOpenError("Не удалось сохранить книгу. Повторите /suggest.")

    kind = pending.get("kind")
    if kind == "catalog":
        raw = pending.get("book")
        if not isinstance(raw, dict):
            raise CycleNotOpenError("Не удалось сохранить книгу. Повторите /suggest.")
        schema = BookSchema.model_validate(raw)
        return await CycleService(session).add_suggestion(user, schema)
    if kind == "manual":
        title = pending.get("title")
        if not isinstance(title, str) or not title:
            raise CycleNotOpenError("Не удалось сохранить книгу. Повторите /suggest.")
        authors = pending.get("authors")
        description = pending.get("description")
        pages = pending.get("page_count")
        cover_url = pending.get("cover_url")
        return await ManualBookService(session).add(
            user,
            title=title,
            authors=authors if isinstance(authors, str) else None,
            description=description if isinstance(description, str) else None,
            page_count=pages if isinstance(pages, int) else None,
            cover_url=cover_url if isinstance(cover_url, str) else None,
        )
    raise CycleNotOpenError("Не удалось сохранить книгу. Повторите /suggest.")


async def _publish_to_group(
    bot: Bot,
    session: AsyncSession,
    book: Book,
    user: User,
) -> bool:
    dest = await DestinationService(session).get_destination()
    if dest is None:
        return False
    try:
        await send_html_card(
            bot,
            dest.chat_id,
            format_group_card(book, user),
            book.cover_url,
            dest.message_thread_id,
        )
    except TelegramBadRequest:
        return False
    return True


async def _send_book_card(message: Message, cover_url: str | None, caption: str) -> None:
    if cover_url:
        try:
            await message.answer_photo(
                photo=cover_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            return
        except TelegramBadRequest:
            try:
                await message.answer_document(
                    document=cover_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
                return
            except TelegramBadRequest:
                pass

    await message.answer(caption, parse_mode=ParseMode.HTML)


async def _finish_manual_card(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    cover_url: str | None,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    title = data.get("manual_title")
    authors = data.get("manual_authors")
    page_count = data.get("manual_pages")
    description = data.get("manual_description")
    if not isinstance(title, str) or not title:
        await state.clear()
        await message.answer(
            "Не удалось сохранить книгу. Повторите /suggest.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.update_data(
        pending={
            "kind": "manual",
            "title": title,
            "authors": authors if isinstance(authors, str) else None,
            "description": description if isinstance(description, str) else None,
            "page_count": page_count if isinstance(page_count, int) else None,
            "cover_url": cover_url,
        }
    )
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    preview = _preview_book(await state.get_data())
    if preview is None:
        await state.clear()
        await message.answer(
            "Не удалось подготовить карточку. Повторите /suggest.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await _ask_confirm(message, state, preview, user)


def _cover_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    document = message.document
    if document is None:
        return None
    mime = (document.mime_type or "").lower()
    if mime.startswith("image/"):
        return document.file_id
    return None
