from __future__ import annotations

import logging

from aiohttp import web

from app.core.config import get_settings
from app.services.meeting_invite import ICS_CONTENT_TYPE, ICS_FILENAME, invite_from_token

logger = logging.getLogger(__name__)


def create_calendar_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/invite/{token}.ics", calendar_ics_handler)
    return app


async def calendar_ics_handler(request: web.Request) -> web.StreamResponse:
    invite = invite_from_token(request.match_info["token"])
    if invite is None:
        raise web.HTTPNotFound(text="invite not found")
    return web.Response(
        body=invite.ics_bytes,
        headers={
            "Content-Type": ICS_CONTENT_TYPE,
            "Content-Disposition": f'inline; filename="{ICS_FILENAME}"',
        },
    )


async def start_calendar_http() -> web.AppRunner:
    settings = get_settings()
    runner = web.AppRunner(create_calendar_app())
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.CALENDAR_HTTP_PORT)
    await site.start()
    logger.info("Calendar ICS HTTP on 0.0.0.0:%s", settings.CALENDAR_HTTP_PORT)
    if settings.PUBLIC_BASE_URL is None:
        logger.info("PUBLIC_BASE_URL is not set: iPhone button uses hosted ICS link")
    return runner


async def stop_calendar_http(runner: web.AppRunner) -> None:
    await runner.cleanup()
