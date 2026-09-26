from datetime import date

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin_filter import AdminFilter
from app.bot.club_chat import send_html_card
from app.bot.club_context import club_from_state, remember_club, require_admin_club
from app.bot.callbacks.meeting import MeetingPollBookCallback
from app.bot.club_publish import (
    notify_admins,
    publish_meeting_poll,
    publish_meeting_time_poll,
    publish_vote_polls,
    publish_winner_announcement,
    send_pending_card_reviews,
    stop_meeting_polls,
    stop_meeting_time_polls,
    stop_polls_quietly,
    stop_vote_polls,
)
from app.bot.commands import setup_bot_commands
from app.bot.keyboards.meeting import meeting_poll_book_keyboard
from app.bot.states.meeting import MeetingPollStates
from app.db.models import SuggestionCycle
from app.repositories.settings_repo import SettingsRepository
from app.services.club_destination import (
    ClubDestination,
    DestinationService,
    club_label,
    destination_of,
)
from app.services.cycle_service import (
    CycleNotOpenError,
    CycleNotVotingError,
    CycleService,
    GroupNotSetError,
    MeetingPollsAlreadyOpenError,
    MeetingTimePollsAlreadyOpenError,
    NoCycleError,
    NoOpenMeetingPollsError,
    NoOpenMeetingTimePollsError,
    NoOpenPollsError,
    NotEnoughBooksError,
    NoWinnerError,
    PendingGroupCardsNeedReviewError,
    VotePollsAlreadyOpenError,
    chunk_books_for_polls,
    month_name_ru,
)
from app.services.meeting_poll import (
    chunk_dates_for_polls,
    chunk_hours_for_polls,
    format_meeting_day,
    format_meeting_hour,
    format_manual_meeting_title,
    meeting_date_admin_prompt,
    meeting_date_announcement,
    meeting_poll_options,
    meeting_runoff_options,
    meeting_subject,
    meeting_time_admin_prompt,
    meeting_time_announcement,
    meeting_time_poll_options,
    meeting_time_runoff_options,
    merge_date_counts,
    merge_hour_counts,
    tally_meeting_dates,
    tally_meeting_hours,
)
from app.services.vote_close import VoteCounts, winner_announcement

router = Router()
router.message.filter(AdminFilter())
dm_router = Router()
dm_router.message.filter(F.chat.type == ChatType.PRIVATE)
dm_router.callback_query.filter(AdminFilter(), F.message.chat.type == ChatType.PRIVATE)

_CLEAR_TOPIC = frozenset({"clear", "off", "none", "сброс"})
_MEETING_POLL_STATES = StateFilter(MeetingPollStates)
_ASK_POLL_TITLE = "Напишите название книги для опроса дат."
_ASK_POLL_BOOK = "Встреча по книге месяца или для другой книги?"
_POLL_CANCELLED = "Запуск опроса дат отменён."


@router.message(Command("set_group"))
async def cmd_set_group(message: Message, session: AsyncSession, bot: Bot) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Эту команду нужно вызвать в группе клуба.")
        return

    repo = SettingsRepository(session)
    await repo.bind_group(message.chat.id, message.chat.title)
    clubs = await repo.list_bound()
    await setup_bot_commands(
        bot,
        [club.group_chat_id for club in clubs if club.group_chat_id is not None],
    )
    await message.answer(
        "Группа привязана. Анонсы и опросы будут публиковаться здесь.\n"
        "Чтобы слать предложения в отдельный топик, вызовите /set_suggest_topic из этой ветки."
    )


@router.message(Command("set_suggest_topic"))
async def cmd_set_suggest_topic(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
) -> None:
    arg = (command.args or "").strip().casefold()
    if arg in _CLEAR_TOPIC:
        if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            club = await SettingsRepository(session).get_by_chat_id(message.chat.id)
            if club is None:
                await message.answer("Сначала привяжите эту группу командой /set_group.")
                return
        else:
            club = await require_admin_club(message, bot, session)
            if club is None:
                return
        await DestinationService(session, club).clear_suggest_topic()
        await message.answer(
            "Топик предложений сброшен. Можно предлагать в любом месте группы."
        )
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

    club = await SettingsRepository(session).get_by_chat_id(message.chat.id)
    if club is None:
        await message.answer("Сначала привяжите эту группу командой /set_group.")
        return

    try:
        settings = await DestinationService(session, club).bind_suggest_topic(
            message.chat.id, thread_id
        )
    except GroupNotSetError as exc:
        await message.answer(str(exc))
        return

    await message.answer(f"Топик предложений привязан (id {settings.suggest_topic_id}).")


@dm_router.message(Command("start_vote"))
async def cmd_start_vote(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle, chunks = await service.prepare_vote()
    except CycleNotOpenError as exc:
        await message.answer(str(exc))
        return
    except VotePollsAlreadyOpenError as exc:
        await message.answer(str(exc))
        return
    except PendingGroupCardsNeedReviewError as exc:
        await send_pending_card_reviews(bot, exc.cards, session)
        await message.answer("Сначала проверьте карточки из группы в личке.")
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


@dm_router.message(Command("close_vote"))
async def cmd_close_vote(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
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
            await publish_winner_announcement(
                bot,
                dest,
                winner_announcement(cycle, winner),
                winner.cover_url,
            )
        except TelegramAPIError as exc:
            await message.answer(f"Книга выбрана, но анонс не отправился: {exc}")
            return
        try:
            ok = await _publish_and_record_meeting_poll(
                bot, dest, service, cycle, meeting_subject(cycle, winner)
            )
        except TelegramAPIError as exc:
            await message.answer(
                f"Книга выбрана, но опрос дат встречи не отправился: {exc}\n"
                "Можно повторить командой /start_meeting_poll."
            )
            return
        if not ok:
            await message.answer(
                "Книга выбрана, но опрос дат встречи не записался.\n"
                "Можно повторить командой /start_meeting_poll."
            )
            return
        if not same_thread:
            await message.answer(
                "Голосование закрыто. Опрос дат встречи опубликован в группе."
            )
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


@dm_router.message(Command("reset_vote"))
async def cmd_reset_vote(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        plan = await service.prepare_vote_reset()
    except NoCycleError as exc:
        await message.answer(str(exc))
        return
    except PendingGroupCardsNeedReviewError as exc:
        await send_pending_card_reviews(bot, exc.cards, session)
        await message.answer("Сначала проверьте карточки из группы в личке.")
        return
    except NotEnoughBooksError as exc:
        await message.answer(str(exc))
        return

    await stop_polls_quietly(
        bot,
        [*plan.open_vote_polls, *plan.open_meeting_polls, *plan.open_meeting_time_polls],
    )
    cycle = await service.apply_vote_reset(plan)

    try:
        published = await publish_vote_polls(bot, dest, cycle, plan.chunks)
    except TelegramAPIError as exc:
        await message.answer(f"Старые опросы закрыты, но новые не отправились: {exc}")
        return

    await service.record_vote_polls(cycle, published)
    await service.mark_voting(cycle)
    started = plan.period_start
    await message.answer(
        f"Голосование сброшено. Новые опросы с {plan.book_count} книгами "
        f"с {started.day:02d}.{started.month:02d}.{started.year}."
    )


@dm_router.message(Command("start_meeting_poll"))
async def cmd_start_meeting_poll(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle = await service.prepare_meeting_poll()
    except (CycleNotOpenError, MeetingPollsAlreadyOpenError) as exc:
        await message.answer(str(exc))
        return

    book = await service.book_for_cycle(cycle)
    if book is None:
        await remember_club(state, club)
        await state.update_data(meeting_title_override=False)
        await state.set_state(MeetingPollStates.waiting_title)
        await message.answer(_ASK_POLL_TITLE)
        return

    await remember_club(state, club)
    await state.set_state(MeetingPollStates.waiting_book_choice)
    await message.answer(_ASK_POLL_BOOK, reply_markup=meeting_poll_book_keyboard())


@dm_router.callback_query(
    MeetingPollStates.waiting_book_choice,
    MeetingPollBookCallback.filter(),
)
async def on_meeting_poll_book_choice(
    callback: CallbackQuery,
    callback_data: MeetingPollBookCallback,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    origin = callback.message
    if origin is None:
        await callback.answer()
        return

    club = await club_from_state(state, session)
    if club is None:
        user = callback.from_user
        club = await require_admin_club(
            origin,
            bot,
            session,
            user_id=None if user is None else user.id,
        )
    if club is None:
        await callback.answer()
        await state.clear()
        return
    dest = destination_of(club)
    if dest is None:
        await callback.answer()
        await state.clear()
        await origin.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle = await service.prepare_meeting_poll()
    except (CycleNotOpenError, MeetingPollsAlreadyOpenError) as exc:
        await callback.answer()
        await state.clear()
        await origin.answer(str(exc))
        return

    with suppress(TelegramAPIError):
        await origin.edit_reply_markup(reply_markup=None)

    if callback_data.action == "other":
        await remember_club(state, club)
        await state.update_data(meeting_title_override=True)
        await state.set_state(MeetingPollStates.waiting_title)
        await callback.answer()
        await origin.answer(_ASK_POLL_TITLE)
        return

    book = await service.book_for_cycle(cycle)
    await service.clear_meeting_title(cycle)
    await callback.answer()
    await state.clear()
    await _finish_meeting_poll(origin, bot, dest, service, cycle, meeting_subject(cycle, book))


@dm_router.message(Command("cancel"), _MEETING_POLL_STATES)
async def cmd_cancel_meeting_poll(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_POLL_CANCELLED)


@dm_router.message(
    MeetingPollStates.waiting_title,
    F.text,
    ~F.text.startswith("/"),
)
async def on_meeting_poll_title(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    title = format_manual_meeting_title(message.text or "")
    if not title:
        await message.answer(_ASK_POLL_TITLE)
        return

    club = await club_from_state(state, session)
    if club is None:
        club = await require_admin_club(message, bot, session)
    if club is None:
        await state.clear()
        return
    dest = destination_of(club)
    if dest is None:
        await state.clear()
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle = await service.prepare_meeting_poll()
    except (CycleNotOpenError, MeetingPollsAlreadyOpenError) as exc:
        await state.clear()
        await message.answer(str(exc))
        return

    data = await state.get_data()
    override = data.get("meeting_title_override") is True
    if override:
        await service.apply_meeting_title(cycle, title)
        book = await service.book_for_cycle(cycle)
    else:
        book = await service.apply_manual_meeting_book(cycle, title)
    await state.clear()
    await _finish_meeting_poll(message, bot, dest, service, cycle, meeting_subject(cycle, book))


@dm_router.message(Command("close_meeting_poll"))
async def cmd_close_meeting_poll(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle = await service.get_meeting_poll_cycle()
        polls = await service.require_open_meeting_polls(cycle)
    except (CycleNotOpenError, NoOpenMeetingPollsError) as exc:
        await message.answer(str(exc))
        return

    book = await service.book_for_cycle(cycle)

    try:
        stopped = await stop_meeting_polls(bot, polls)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось закрыть опрос дат: {exc}")
        return

    for poll in polls:
        await service.mark_meeting_poll_closed(poll)

    tallies = merge_date_counts(
        [tally_meeting_dates(poll.option_dates, options) for poll, options in stopped]
    )
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if tallies.total == 0:
        await message.answer(
            "Никто не выбрал день. Можно запустить опрос заново командой /start_meeting_poll."
        )
        return

    leaders = tallies.leaders()
    if len(leaders) == 1:
        winner_day = leaders[0]
        await service.apply_meeting_date(cycle, winner_day)
        try:
            await publish_winner_announcement(
                bot,
                dest,
                meeting_date_announcement(cycle, book, winner_day),
            )
        except TelegramAPIError as exc:
            await message.answer(f"Дата выбрана, но анонс не отправился: {exc}")
            return
        await notify_admins(bot, meeting_date_admin_prompt(book, winner_day), dest.chat_id)
        if not same_thread:
            await message.answer("Опрос дат закрыт. Дата встречи опубликована в группе.")
        return

    chunks = chunk_dates_for_polls(leaders)
    try:
        for index, chunk in enumerate(chunks):
            published = await publish_meeting_poll(
                bot,
                dest,
                meeting_subject(cycle, book),
                meeting_runoff_options(chunk),
                runoff=True,
                send_intro=index == 0,
            )
            if published is None:
                await message.answer("Ничья, но второй тур не записался.")
                return
            await service.record_meeting_poll(cycle, published)
    except TelegramAPIError as exc:
        await message.answer(f"Ничья, но второй тур не отправился: {exc}")
        return
    if not same_thread:
        await message.answer("Ничья. Второй тур по датам опубликован в группе.")


@dm_router.message(Command("start_meeting_time_poll"))
async def cmd_start_meeting_time_poll(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle = await service.prepare_meeting_time_poll()
    except (CycleNotOpenError, MeetingTimePollsAlreadyOpenError) as exc:
        await message.answer(str(exc))
        return

    book = await service.book_for_cycle(cycle)
    await _finish_meeting_time_poll(
        message,
        bot,
        dest,
        service,
        cycle,
        meeting_subject(cycle, book),
        cycle.winner_meeting_date,
    )


@dm_router.message(Command("close_meeting_time_poll"))
async def cmd_close_meeting_time_poll(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    dest = destination_of(club)
    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    service = CycleService(session, club)
    try:
        cycle = await service.get_meeting_poll_cycle()
        polls = await service.require_open_meeting_time_polls(cycle)
    except (CycleNotOpenError, NoOpenMeetingTimePollsError) as exc:
        await message.answer(str(exc))
        return

    book = await service.book_for_cycle(cycle)

    try:
        stopped = await stop_meeting_time_polls(bot, polls)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось закрыть опрос времени: {exc}")
        return

    for poll in polls:
        await service.mark_meeting_time_poll_closed(poll)

    tallies = merge_hour_counts(
        [tally_meeting_hours(poll.option_hours, options) for poll, options in stopped]
    )
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if tallies.total == 0:
        await message.answer(
            "Никто не выбрал время. Можно запустить опрос заново командой /start_meeting_time_poll."
        )
        return

    leaders = tallies.leaders()
    if len(leaders) == 1:
        winner_hour = leaders[0]
        await service.apply_meeting_hour(cycle, winner_hour)
        try:
            await publish_winner_announcement(
                bot,
                dest,
                meeting_time_announcement(cycle, book, cycle.winner_meeting_date, winner_hour),
            )
        except TelegramAPIError as exc:
            await message.answer(f"Время выбрано, но анонс не отправился: {exc}")
            return
        await notify_admins(
            bot,
            meeting_time_admin_prompt(book, cycle.winner_meeting_date, winner_hour),
            dest.chat_id,
        )
        if not same_thread:
            await message.answer("Опрос времени закрыт. Время встречи опубликовано в группе.")
        return

    chunks = chunk_hours_for_polls(leaders)
    try:
        for index, chunk in enumerate(chunks):
            published = await publish_meeting_time_poll(
                bot,
                dest,
                meeting_subject(cycle, book),
                meeting_time_runoff_options(chunk),
                day=cycle.winner_meeting_date,
                runoff=True,
                send_intro=index == 0,
            )
            if published is None:
                await message.answer("Ничья, но второй тур не записался.")
                return
            await service.record_meeting_time_poll(cycle, published)
    except TelegramAPIError as exc:
        await message.answer(f"Ничья, но второй тур не отправился: {exc}")
        return
    if not same_thread:
        await message.answer("Ничья. Второй тур по времени опубликован в группе.")


@dm_router.message(Command("cycle_status"))
async def cmd_cycle_status(message: Message, session: AsyncSession, bot: Bot) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    service = CycleService(session, club)
    settings = club
    cycle = await service.get_latest_cycle()

    group = club_label(club)
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
        pending = await service.count_pending_group_cards(cycle.id)
        if pending:
            lines.append(f"Карточек на проверке: {pending}")
        if cycle.winner_book_id is not None:
            chosen = await service.books_by_ids([cycle.winner_book_id])
            if chosen:
                lines.append(f"Выбранная книга: {chosen[0].title}")
        if cycle.winner_meeting_date is not None:
            meeting_line = f"Дата встречи: {format_meeting_day(cycle.winner_meeting_date)}"
            if cycle.winner_meeting_hour is not None:
                meeting_line += f", {format_meeting_hour(cycle.winner_meeting_hour)}"
            lines.append(meeting_line)
        elif cycle.winner_meeting_hour is not None:
            lines.append(f"Время встречи: {format_meeting_hour(cycle.winner_meeting_hour)}")

    await message.answer("\n".join(lines))


@dm_router.message(Command("month_book"))
async def cmd_month_book(message: Message, session: AsyncSession, bot: Bot) -> None:
    club = await require_admin_club(message, bot, session)
    if club is None:
        return
    service = CycleService(session, club)
    try:
        cycle = await service.get_selected_cycle()
    except NoWinnerError as exc:
        await message.answer(str(exc))
        return

    book = cycle.winner
    if book is None:
        await message.answer("Сначала закройте голосование за книгу командой /close_vote.")
        return

    await send_html_card(
        bot,
        message.chat.id,
        winner_announcement(cycle, book),
        book.cover_url,
        message.message_thread_id,
        parse_mode=None,
    )


async def _finish_meeting_poll(
    message: Message,
    bot: Bot,
    dest: ClubDestination,
    service: CycleService,
    cycle: SuggestionCycle,
    title: str,
) -> None:
    try:
        ok = await _publish_and_record_meeting_poll(bot, dest, service, cycle, title)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось опубликовать опрос дат: {exc}")
        return
    if not ok:
        await message.answer(
            "Не удалось записать опрос дат. Попробуйте /start_meeting_poll ещё раз."
        )
        return
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if not same_thread:
        await message.answer("Опрос дат встречи опубликован в группе.")


async def _publish_and_record_meeting_poll(
    bot: Bot,
    dest: ClubDestination,
    service: CycleService,
    cycle: SuggestionCycle,
    title: str,
) -> bool:
    published = await publish_meeting_poll(
        bot,
        dest,
        title,
        meeting_poll_options(),
    )
    if published is None:
        return False
    await service.record_meeting_poll(cycle, published)
    return True


async def _finish_meeting_time_poll(
    message: Message,
    bot: Bot,
    dest: ClubDestination,
    service: CycleService,
    cycle: SuggestionCycle,
    title: str,
    day: date | None,
) -> None:
    try:
        ok = await _publish_and_record_meeting_time_poll(bot, dest, service, cycle, title, day)
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось опубликовать опрос времени: {exc}")
        return
    if not ok:
        await message.answer(
            "Не удалось записать опрос времени. Попробуйте /start_meeting_time_poll ещё раз."
        )
        return
    same_thread = (
        message.chat.id == dest.chat_id and message.message_thread_id == dest.message_thread_id
    )
    if not same_thread:
        await message.answer("Опрос времени встречи опубликован в группе.")


async def _publish_and_record_meeting_time_poll(
    bot: Bot,
    dest: ClubDestination,
    service: CycleService,
    cycle: SuggestionCycle,
    title: str,
    day: date | None,
) -> bool:
    published = await publish_meeting_time_poll(
        bot,
        dest,
        title,
        meeting_time_poll_options(),
        day=day,
    )
    if published is None:
        return False
    await service.record_meeting_time_poll(cycle, published)
    return True


router.include_router(dm_router)
