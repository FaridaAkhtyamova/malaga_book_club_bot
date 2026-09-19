from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    BotCommandScopeDefault,
)

from app.bot.club_chat import club_admin_user_ids
from app.services.hashtag_suggest import CARD_TEMPLATE

_HASHTAG_HINT = (
    "В группе, пока сбор открыт, запостите карточку: после тега название, затем автор. "
    "Страницы — в любой строке со словами «стр» / «страниц». Кто предложил — из сообщения.\n"
    f"{CARD_TEMPLATE}"
)


@dataclass(frozen=True, slots=True)
class CommandInfo:
    command: str
    menu_description: str
    help_line: str
    admin: bool = False
    group_setup: bool = False


COMMANDS: tuple[CommandInfo, ...] = (
    CommandInfo(
        "start",
        "Приветствие и как предложить книгу",
        "/start — приветствие и как предложить книгу (личка с ботом)",
    ),
    CommandInfo("help", "Список команд", "/help — это сообщение"),
    CommandInfo(
        "suggest",
        "Найти книгу в каталоге (личка)",
        "/suggest — поиск книги в каталоге (личка с ботом)\n"
        "/suggest Название — то же, сразу с названием",
    ),
    CommandInfo(
        "clubs",
        "Список клубов и переключение",
        "/clubs — список групп, к которым есть доступ, и выбор клуба для команд в личке",
    ),
    CommandInfo(
        "cancel",
        "Отменить текущий ввод",
        "/cancel — отменить поиск, проверку карточки, опрос дат или создание встречи",
    ),
    CommandInfo(
        "set_group",
        "Привязать эту группу как клубную",
        "/set_group — запомнить эту группу как клубную (только из группы; "
        "каждая группа — отдельный клуб)",
        admin=True,
        group_setup=True,
    ),
    CommandInfo(
        "set_suggest_topic",
        "Привязать топик предложений",
        "/set_suggest_topic — привязать топик предложений (вызвать из ветки)\n"
        "/set_suggest_topic clear — сбросить топик (личка с ботом)",
        admin=True,
        group_setup=True,
    ),
    CommandInfo(
        "set_suggest_day",
        "День автооткрытия сбора книг",
        "/set_suggest_day 15 — каждый месяц 15-го открывать сбор (день от 1 до 28)",
        admin=True,
    ),
    CommandInfo(
        "set_vote_day",
        "День автозапуска голосования",
        "/set_vote_day 25 — каждый месяц 25-го запускать опросы (позже дня сбора)",
        admin=True,
    ),
    CommandInfo(
        "open_suggestions",
        "Открыть сбор книг на следующий месяц",
        "/open_suggestions — открыть сбор на следующий месяц и анонсировать в группе",
        admin=True,
    ),
    CommandInfo(
        "start_vote",
        "Закрыть сбор и опубликовать опросы",
        "/start_vote — проверить ручные карточки и опубликовать голосовалки",
        admin=True,
    ),
    CommandInfo(
        "close_vote",
        "Закрыть опросы и выбрать книгу",
        "/close_vote — закрыть опросы, выбрать книгу "
        "или запустить второй тур при ничьей",
        admin=True,
    ),
    CommandInfo(
        "reset_vote",
        "Сбросить голосование и открыть заново",
        "/reset_vote — закрыть текущие опросы без выбора победителя "
        "и открыть голосование заново с книгами с 1-го числа месяца сбора",
        admin=True,
    ),
    CommandInfo(
        "start_meeting_poll",
        "Опрос дат встречи",
        "/start_meeting_poll — опрос дат встречи (если книги нет — сначала спросит название)",
        admin=True,
    ),
    CommandInfo(
        "close_meeting_poll",
        "Закрыть опрос дат и выбрать день",
        "/close_meeting_poll — закрыть опрос дат, выбрать день "
        "или запустить второй тур при ничьей",
        admin=True,
    ),
    CommandInfo(
        "create_meeting",
        "Приглашение в календарь",
        "/create_meeting — спросить дату (если нет опроса дат), название книги "
        "(если её нет) и время, затем опубликовать приглашение",
        admin=True,
    ),
    CommandInfo(
        "cycle_status",
        "Текущие настройки и цикл",
        "/cycle_status — клуб, топик, дни, месяц и сколько книг уже предложено",
        admin=True,
    ),
    CommandInfo(
        "month_book",
        "Книга месяца",
        "/month_book — выбранная книга месяца (победитель голосования)",
        admin=True,
    ),
)


def _menu_commands(*, admin: bool | None, group_setup: bool | None = None) -> list[BotCommand]:
    return [
        BotCommand(command=item.command, description=item.menu_description)
        for item in COMMANDS
        if (admin is None or item.admin is admin)
        and (group_setup is None or item.group_setup is group_setup)
    ]


def member_bot_commands() -> list[BotCommand]:
    return _menu_commands(admin=False)


def admin_bot_commands() -> list[BotCommand]:
    return _menu_commands(admin=None)


def group_setup_bot_commands() -> list[BotCommand]:
    return _menu_commands(admin=True, group_setup=True)


def admin_command_names() -> tuple[str, ...]:
    return tuple(item.command for item in COMMANDS if item.admin)


def format_help(*, is_admin: bool) -> str:
    lines = [
        "Команды пишите в личке с ботом.",
        "В группе бот только публикует анонсы, опросы, карточки и приглашения.",
        "",
        "Команды для всех:",
        "",
    ]
    lines.extend(item.help_line for item in COMMANDS if not item.admin)
    lines.extend(["", _HASHTAG_HINT])
    if not is_admin:
        return "\n".join(lines)

    lines.extend(["", "Команды для админа:", ""])
    lines.extend(item.help_line for item in COMMANDS if item.admin)
    lines.append("")
    lines.append(
        "Админские команды — тоже в личке и относятся к выбранному клубу "
        "(/clubs, если групп несколько). "
        "Исключения: /set_group и /set_suggest_topic — только из группы."
    )
    return "\n".join(lines)


async def setup_bot_commands(
    bot: Bot,
    club_chat_ids: int | Sequence[int] | None = None,
) -> None:
    await bot.set_my_commands(member_bot_commands(), scope=BotCommandScopeDefault())
    await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
    if isinstance(club_chat_ids, int):
        ids = [club_chat_ids]
    else:
        ids = [chat_id for chat_id in (club_chat_ids or []) if chat_id is not None]
    if not ids:
        return

    seen_admins: set[int] = set()
    for chat_id in ids:
        with suppress(TelegramBadRequest):
            await bot.set_my_commands(
                group_setup_bot_commands(),
                scope=BotCommandScopeChatAdministrators(chat_id=chat_id),
            )
        for admin_id in await club_admin_user_ids(bot, chat_id):
            if admin_id in seen_admins:
                continue
            seen_admins.add(admin_id)
            try:
                await bot.set_my_commands(
                    admin_bot_commands(),
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except TelegramBadRequest:
                continue
