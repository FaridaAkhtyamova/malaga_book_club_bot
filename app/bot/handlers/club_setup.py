from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.club_publish import (
    publish_meeting_poll,
    publish_vote_polls,
    publish_winner_announcement,
    stop_vote_polls,
)
from app.bot.filters.admin_filter import AdminFilter
from app.services.club_destination import DestinationService
from app.services.cycle_service import (
    CycleNotOpenError,
    CycleNotVotingError,
    CycleService,
    GroupNotSetError,
    NoOpenPollsError,
    NoWinnerError,
    NotEnoughBooksError,
    VotePollsAlreadyOpenError,
    chunk_books_for_polls,
    month_name_ru,
)
from app.services.meeting_poll import meeting_poll_options
from app.services.vote_close import VoteCounts, winner_announcement

router = Router()

_CLEAR_TOPIC = frozenset({"clear", "off", "none", "сброс"})


@router.message(Command("set_group"), AdminFilter())
async def cmd_set_group(message: Message, session: AsyncSession) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Эту команду нужно вызвать в группе клуба.")
        return

    service = CycleService(session)
    previous = (await service.get_settings()).group_chat_id
    await service.bind_group(message.chat.id)
    await DestinationService(session).clear_topic_if_group_changed(previous, message.chat.id)
    await message.answer(
        "Группа привязана. Анонсы и опросы будут публиковаться здесь.\n"
        "Чтобы слать предложения в отдельный топик, вызовите /set_suggest_topic из этой ветки."
    )


@router.message(Command("set_suggest_topic"), AdminFilter())
async def cmd_set_suggest_topic(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
) -> None:
    dest_service = DestinationService(session)
    arg = (command.args or "").strip().casefold()
    if arg in _CLEAR_TOPIC:
        await dest_service.clear_suggest_topic()
        await message.answer("Топик предложений сброшен. Можно предлагать в любом месте группы.")
        return

    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer(
            "Вызовите команду из топика в группе клуба. Сброс: /set_suggest_topic clear"
        )
        return

    thread_id = message.message_thread_id
    if thread_id is None:
        await message.answer(
            "Включите топики и вызовите /set_suggest_topic из нужной ветки. "
            "Сброс: /set_suggest_topic clear"
        )
        return

    try:
        settings = await dest_service.bind_suggest_topic(message.chat.id, thread_id)
    except GroupNotSetError as exc:
        await message.answer(str(exc))
        return

    await message.answer(f"Топик предложений привязан (id {settings.suggest_topic_id}).")


@router.message(Command("start_vote"), AdminFilter())
async def cmd_start_vote(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    dest = await DestinationService(session).get_destination()
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session)
    try:
        cycle, chunks = await service.prepare_vote()
    except CycleNotOpenError as exc:
        await message.answer(str(exc))
        return
    except VotePollsAlreadyOpenError as exc:
        await message.answer(str(exc))
        return
    except NotEnoughBooksError as exc:
        await message.answer(str(exc))
        return

    try:
        published = await publish_vote_polls(bot, dest, cycle, chunks)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось опубликовать опросы: {exc}")
        return

    await service.record_vote_polls(cycle, published)
    await service.mark_voting(cycle)
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if not same_thread:
        await message.answer("Опросы опубликованы в группе.")


@router.message(Command("close_vote"), AdminFilter())
async def cmd_close_vote(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    dest = await DestinationService(session).get_destination()
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session)
    cycle = await service.get_latest_voting()
    if cycle is None:
        await message.answer("Сейчас нет активного голосования за книгу.")
        return

    try:
        polls = await service.require_open_vote_polls(cycle)
    except (CycleNotVotingError, NoOpenPollsError) as exc:
        await message.answer(str(exc))
        return

    try:
        counts = await stop_vote_polls(bot, polls)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось закрыть опросы: {exc}")
        return

    for poll in polls:
        await service.mark_poll_closed(poll)

    tallies = VoteCounts(by_book=counts)
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if tallies.total == 0:
        await service.reopen_suggestions_after_empty_vote(cycle)
        await message.answer(
            "Никто не проголосовал. Сбор книг снова открыт — можно запустить /start_vote."
        )
        return

    leaders = await service.books_by_ids(tallies.leaders())
    if len(leaders) == 1:
        winner = leaders[0]
        await service.apply_winner(cycle, winner)
        try:
            await publish_winner_announcement(bot, dest, winner_announcement(cycle, winner))
        except TelegramAPIError as exc:
            await message.answer(f"Книга выбрана, но анонс не отправился: {exc}")
            return
        if not same_thread:
            await message.answer("Голосование закрыто, выбранная книга опубликована в группе.")
        return

    chunks = chunk_books_for_polls(leaders)
    try:
        published = await publish_vote_polls(bot, dest, cycle, chunks, runoff=True)
    except TelegramAPIError as exc:
        await message.answer(f"Ничья, но второй тур не отправился: {exc}")
        return
    await service.record_vote_polls(cycle, published)
    if not same_thread:
        await message.answer("Ничья. Второй тур опубликован в группе.")


@router.message(Command("start_meeting_poll"), AdminFilter())
async def cmd_start_meeting_poll(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    dest = await DestinationService(session).get_destination()
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    try:
        book = await CycleService(session).get_selected_book()
    except NoWinnerError as exc:
        await message.answer(str(exc))
        return

    await publish_meeting_poll(bot, dest, book.title, meeting_poll_options())
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if not same_thread:
        await message.answer("Опрос дат встречи опубликован в группе.")


@router.message(Command("cycle_status"), AdminFilter())
async def cmd_cycle_status(message: Message, session: AsyncSession) -> None:
    service = CycleService(session)
    settings = await service.get_settings()
    cycle = await service.get_latest_cycle()

    group = str(settings.group_chat_id) if settings.group_chat_id is not None else "не задана"
    topic = (
        str(settings.suggest_topic_id) if settings.suggest_topic_id is not None else "не задан"
    )
    suggest_day = str(settings.suggest_day) if settings.suggest_day is not None else "не задан"
    vote_day = str(settings.vote_day) if settings.vote_day is not None else "не задан"

    lines = [
        f"Группа: {group}",
        f"Топик предложений: {topic}",
        f"День предложений: {suggest_day}",
        f"День голосования: {vote_day}",
        f"Час анонса: {settings.announce_hour}:00",
    ]

    if cycle is None:
        lines.append("Текущий цикл: нет")
    else:
        count = await service.count_suggestions(cycle.id)
        month = month_name_ru(cycle.target_month)
        lines.append(f"Цикл: {month} {cycle.target_year}, статус {cycle.status}, книг: {count}")
        if cycle.winner_book_id is not None:
            chosen = await service.books_by_ids([cycle.winner_book_id])
            if chosen:
                lines.append(f"Выбранная книга: {chosen[0].title}")

    await message.answer("\n".join(lines))
