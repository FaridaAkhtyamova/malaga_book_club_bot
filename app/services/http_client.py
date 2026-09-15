from __future__ import annotations

import httpx

_HEADERS = {
    "User-Agent": "MalagaBookClubBot/1.0 (book club telegram bot)",
    "Accept": "application/json",
}


def async_http_client(*, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        headers=_HEADERS,
        follow_redirects=True,
        transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1),
    )
