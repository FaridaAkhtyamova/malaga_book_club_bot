from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin_filter import AdminFilter
from app.bot.club_publish import publish_club_announcement
from app.services.club_destination import DestinationService, suggestion_announcement_text
from app.services.cycle_open import CycleOpenService
from app.services.cycle_service import CycleAlreadyOpenError, GroupNotSetError, month_name_ru

router = Router()
router.message.filter(AdminFilter(), F.chat.type == ChatType.PRIVATE)


@router.message(Command("open_suggestions"))
async def cmd_open_suggestions(
    message: Message,
    session: AsyncSession,
    bot: Bot,
) -> None:
    try:
        cycle, _, should_announce = await CycleOpenService(session).open_or_reopen()
        dest = await DestinationService(session).get_destination()
    except GroupNotSetError as exc:
        await message.answer(str(exc))
        return
    except CycleAlreadyOpenError as exc:
        await message.answer(str(exc))
        return

    if dest is None:
        await message.answer("Сначала привяжите группу командой /set_group.")
        return

    month = month_name_ru(cycle.target_month)
    if not should_announce:
        await message.answer(f"Сбор предложений на {month} уже открыт.")
        return

    try:
        await publish_club_announcement(
            bot,
            dest,
            suggestion_announcement_text(cycle.target_month),
        )
    except TelegramBadRequest as exc:
        await message.answer(
            f"Сбор на {month} открыт, но анонс в группу не отправился: {exc}"
        )
        return

    if message.chat.id == dest.chat_id:
        return

    await message.answer(f"Сбор предложений на {month} открыт, анонс опубликован в группе.")
