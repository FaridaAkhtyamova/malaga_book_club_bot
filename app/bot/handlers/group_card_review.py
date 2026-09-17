from __future__ import annotations

from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin_filter import AdminFilter
from app.bot.callbacks.pending_card import PendingCardCallback
from app.bot.media import cover_file_id
from app.bot.states.pending_card import PendingCardStates
from app.db.models import PendingGroupCard
from app.services.cycle_service import CycleNotOpenError
from app.services.pending_group_card import (
    PendingCardNeedsTitleError,
    PendingCardNotFoundError,
    PendingGroupCardService,
)

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

_SKIP = "-"
_KEEP = "."
_REVIEW_STATES = StateFilter(PendingCardStates)
_CANCELLED = "Правка отменена. Карточка всё ещё ждёт проверки."
_QUEUE_EMPTY = "Очередь пуста. Можно запускать /start_vote."


@router.callback_query(PendingCardCallback.filter())
async def on_pending_card(
    callback: CallbackQuery,
    callback_data: PendingCardCallback,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    service = PendingGroupCardService(session)
    message = callback.message if isinstance(callback.message, Message) else None
    if callback_data.action == "edit":
        try:
            card = await service.get_pending(callback_data.card_id)
        except PendingCardNotFoundError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await state.update_data(pending_card_id=card.id)
        await state.set_state(PendingCardStates.waiting_title)
        if message is not None:
            await message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        if message is not None:
            await message.answer(_ask_title(card))
        return

    if callback_data.action == "skip":
        try:
            await service.reject(callback_data.card_id)
        except PendingCardNotFoundError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if message is not None:
            await message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        if message is not None:
            await message.answer(await _after_review(service, callback_data.card_id))
        return

    if callback_data.action != "ok":
        await callback.answer()
        return

    if callback.from_user is not None:
        try:
            card = await service.get_pending(callback_data.card_id)
        except PendingCardNotFoundError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await _ensure_cover(bot, service, card, callback.from_user.id)

    try:
        _, created = await service.approve(callback_data.card_id)
    except PendingCardNeedsTitleError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except (PendingCardNotFoundError, CycleNotOpenError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    if message is not None:
        await message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    if message is None:
        return
    added = "Книга в списке на голосование." if created else "Эта книга уже была в списке."
    leftover = await _after_review(service, callback_data.card_id)
    await message.answer(f"{added}\n{leftover}")


@router.message(Command("cancel"), _REVIEW_STATES)
async def cmd_cancel_review(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_CANCELLED)


@router.message(PendingCardStates.waiting_title, F.text)
async def process_review_title(message: Message, state: FSMContext, session: AsyncSession) -> None:
    card = await _card_from_state(state, session)
    if card is None:
        await state.clear()
        await message.answer("Эта карточка уже разобрана или не найдена.")
        return
    raw = (message.text or "").strip()
    if raw == _KEEP:
        title = (card.title or "").strip()
    else:
        title = raw
    if not title:
        await message.answer("Нужно название. Отправьте его текстом.")
        return
    await state.update_data(review_title=title)
    await state.set_state(PendingCardStates.waiting_authors)
    await message.answer(_ask_optional("Автор(ы)", card.authors))


@router.message(PendingCardStates.waiting_authors, F.text)
async def process_review_authors(message: Message, state: FSMContext, session: AsyncSession) -> None:
    card = await _card_from_state(state, session)
    if card is None:
        await state.clear()
        await message.answer("Эта карточка уже разобрана или не найдена.")
        return
    authors = _optional_text(message.text, card.authors)
    await state.update_data(review_authors=authors)
    await state.set_state(PendingCardStates.waiting_pages)
    current = str(card.page_count) if card.page_count is not None else None
    await message.answer(_ask_optional("Число страниц", current))


@router.message(PendingCardStates.waiting_pages, F.text)
async def process_review_pages(message: Message, state: FSMContext, session: AsyncSession) -> None:
    card = await _card_from_state(state, session)
    if card is None:
        await state.clear()
        await message.answer("Эта карточка уже разобрана или не найдена.")
        return
    raw = (message.text or "").strip()
    page_count: int | None
    if raw == _KEEP:
        page_count = card.page_count
    elif raw == _SKIP:
        page_count = None
    elif raw.isdigit() and int(raw) > 0:
        page_count = int(raw)
    else:
        await message.answer(
            "Введите целое число страниц, `.` чтобы оставить или `-` чтобы сбросить."
        )
        return
    await state.update_data(review_pages=page_count)
    await state.set_state(PendingCardStates.waiting_description)
    await message.answer(_ask_optional("Описание", card.description))


@router.message(PendingCardStates.waiting_description, F.text)
async def process_review_description(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    card = await _card_from_state(state, session)
    if card is None:
        await state.clear()
        await message.answer("Эта карточка уже разобрана или не найдена.")
        return
    data = await state.get_data()
    title = data.get("review_title")
    if not isinstance(title, str) or not title.strip():
        await state.clear()
        await message.answer("Не удалось сохранить название. Нажмите «Исправить» ещё раз.")
        return
    authors_raw = data.get("review_authors")
    authors = authors_raw if isinstance(authors_raw, str) else None
    pages_raw = data.get("review_pages")
    page_count = pages_raw if isinstance(pages_raw, int) else None
    description = _optional_text(message.text, card.description)
    service = PendingGroupCardService(session)
    try:
        await service.apply_edits(
            card.id,
            title=title.strip(),
            authors=authors,
            description=description,
            page_count=page_count,
        )
        if message.from_user is not None:
            await _ensure_cover(bot, service, card, message.from_user.id)
        _, created = await service.approve(card.id)
    except PendingCardNeedsTitleError as exc:
        await message.answer(str(exc))
        return
    except (PendingCardNotFoundError, CycleNotOpenError) as exc:
        await state.clear()
        await message.answer(str(exc))
        return

    await state.clear()
    added = "Книга в списке на голосование." if created else "Эта книга уже была в списке."
    leftover = await _after_review(service, card.id)
    await message.answer(f"{added}\n{leftover}")


async def _ensure_cover(
    bot: Bot,
    service: PendingGroupCardService,
    card: PendingGroupCard,
    admin_id: int,
) -> None:
    if card.cover_url:
        return
    try:
        copied = await bot.forward_message(
            chat_id=admin_id,
            from_chat_id=card.chat_id,
            message_id=card.message_id,
        )
    except TelegramAPIError:
        return
    file_id = cover_file_id(copied)
    copied_id = getattr(copied, "message_id", None)
    if isinstance(copied_id, int):
        with suppress(TelegramAPIError):
            await bot.delete_message(admin_id, copied_id)
    if file_id:
        await service.set_cover(card.id, file_id)


async def _card_from_state(state: FSMContext, session: AsyncSession) -> PendingGroupCard | None:
    data = await state.get_data()
    raw_id = data.get("pending_card_id")
    if not isinstance(raw_id, int):
        return None
    try:
        return await PendingGroupCardService(session).get_pending(raw_id)
    except PendingCardNotFoundError:
        return None


def _ask_title(card: PendingGroupCard) -> str:
    current = card.title or "не распознано"
    return (
        f"Название (сейчас: {current}).\n"
        "Отправьте новое или `.` чтобы оставить, если оно уже есть."
    )


def _ask_optional(label: str, current: str | None) -> str:
    shown = current or "нет"
    return (
        f"{label} (сейчас: {shown}).\n"
        "Отправьте новое значение, `.` чтобы оставить или `-` чтобы сбросить."
    )


def _optional_text(raw: str | None, current: str | None) -> str | None:
    text = (raw or "").strip()
    if text == _KEEP:
        return current
    if text == _SKIP:
        return None
    return text or None


async def _after_review(service: PendingGroupCardService, card_id: int) -> str:
    card = await service.get(card_id)
    if card is None:
        return _QUEUE_EMPTY
    leftover = await service.count_pending(card.cycle_id)
    if leftover == 0:
        return _QUEUE_EMPTY
    return f"Ещё на проверке: {leftover}."
