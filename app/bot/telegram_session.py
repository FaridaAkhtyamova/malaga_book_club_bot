from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import InputFile
from aiohttp import FormData

from app.services.meeting_invite import ICS_CONTENT_TYPE


def document_upload_fields(filename: str) -> dict[str, str]:
    extra: dict[str, str] = {"filename": filename}
    if filename.lower().endswith(".ics"):
        extra["content_type"] = ICS_CONTENT_TYPE
    return extra


class CalendarFileSession(AiohttpSession):
    """Upload .ics files as text/calendar so iPhone can hand them to Calendar."""

    def build_form_data(self, bot: Bot, method: TelegramMethod[TelegramType]) -> FormData:
        form = FormData(quote_fields=False)
        files: dict[str, InputFile] = {}
        for key, value in method.model_dump(warnings=False).items():
            prepared = self.prepare_value(value, bot=bot, files=files)
            if not prepared:
                continue
            form.add_field(key, prepared)
        for key, value in files.items():
            form.add_field(key, value.read(bot), **document_upload_fields(value.filename or key))
        return form
