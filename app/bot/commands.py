from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from app.core.config import get_settings

_HASHTAG_HINT = (
    "В группе, пока сбор открыт, можно запостить карточку:\n"
    "#выбор_книги Название книги, 500\n"
    "Краткое описание книги\n"
    "где 500 — количество страниц."
)


@dataclass(frozen=True, slots=True)
class CommandInfo:
    command: str
    menu_description: str
    help_line: str
    admin: bool = False


COMMANDS: tuple[CommandInfo, ...] = (
    CommandInfo(
        "start",
        "Приветствие и как предложить книгу",
        "/start — приветствие и как предложить книгу",
    ),
    CommandInfo("help", "Список команд", "/help — это сообщение"),
    CommandInfo(
        "suggest",
        "Найти книгу в каталоге (личка)",
        "/suggest — поиск книги в каталоге (личка с ботом)\n"
        "/suggest Название — то же, сразу с названием",
    ),
    CommandInfo(
        "cancel",
        "Отменить текущий ввод",
        "/cancel — отменить поиск или создание встречи",
    ),
    CommandInfo(
        "set_group",
        "Привязать эту группу как клубную",
        "/set_group — запомнить эту группу как клубную (только из группы)",
        admin=True,
    ),
    CommandInfo(
        "set_suggest_topic",
        "Привязать топик предложений",
        "/set_suggest_topic — привязать топик предложений (вызвать из ветки)\n"
        "/set_suggest_topic clear — сбросить топик",
        admin=True,
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
        "/start_vote — закрыть сбор и опубликовать голосовалки",
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
        "start_meeting_poll",
        "Опрос дат встречи",
        "/start_meeting_poll — опрос дат встречи (не зависит от голосования за книгу)",
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
        "/create_meeting — спросить время и опубликовать приглашение "
        "(книга и дата уже выбраны)",
        admin=True,
    ),
    CommandInfo(
        "cycle_status",
        "Текущие настройки и цикл",
        "/cycle_status — группа, топик, дни, месяц и сколько книг уже предложено",
        admin=True,
    ),
)


def _menu_commands(*, admin: bool | None) -> list[BotCommand]:
    return [
        BotCommand(command=item.command, description=item.menu_description)
        for item in COMMANDS
        if admin is None or item.admin is admin
    ]


def member_bot_commands() -> list[BotCommand]:
    return _menu_commands(admin=False)


def admin_bot_commands() -> list[BotCommand]:
    return _menu_commands(admin=None)


def format_help(*, is_admin: bool) -> str:
    lines = ["Команды для всех:", ""]
    lines.extend(item.help_line for item in COMMANDS if not item.admin)
    lines.extend(["", _HASHTAG_HINT])
    if not is_admin:
        return "\n".join(lines)

    lines.extend(["", "Команды для админа:", ""])
    lines.extend(item.help_line for item in COMMANDS if item.admin)
    lines.append("")
    lines.append(
        "Админские команды можно писать в группе или в личке с ботом "
        "(кроме /set_group и /set_suggest_topic)."
    )
    return "\n".join(lines)


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(member_bot_commands(), scope=BotCommandScopeDefault())
    admin_commands = admin_bot_commands()
    for admin_id in get_settings().admin_ids:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except TelegramBadRequest:
            continue
