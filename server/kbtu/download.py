"""Bounded HTTPS downloads from the media providers the app uses."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from contextlib import asynccontextmanager

import httpx

TELEGRAM_PAGE = ("t.me",)
TELEGRAM_FILES = ("telesco.pe", "cdn-telegram.org")
TIKTOK_FILES = ("tikwm.com", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokcdn-eu.com", "tiktokv.com")


async def _addresses(host: str) -> list[str]:
    found = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [row[4][0] for row in found]


def allowed(url: str | httpx.URL, hosts: tuple[str, ...]) -> bool:
    try:
        dest = httpx.URL(url)
        return (dest.scheme == "https" and dest.port in (None, 443) and not dest.userinfo
                and any(dest.host == host or dest.host.endswith("." + host) for host in hosts))
    except (ValueError, httpx.InvalidURL):
        return False


@asynccontextmanager
async def stream(http: httpx.AsyncClient, url: str, hosts: tuple[str, ...], *,
                 form: dict | None = None, byte_range: str | None = None, media_headers: dict | None = None):
    """Pin each hop. The original Host and TLS name are preserved for both full files and byte ranges."""
    dest = httpx.URL(url)
    response = None
    try:
        for _ in range(5):
            if not allowed(dest, hosts):
                break
            host = dest.host
            addresses = [ipaddress.ip_address(a) for a in await _addresses(host)]
            if not addresses or any(not a.is_global or a.is_multicast or a.is_reserved for a in addresses):
                break
            headers = {"Host": host, "Connection": "close", "Accept-Encoding": "identity"}
            for name in ("User-Agent", "Referer", "Origin"):
                if value := (media_headers or {}).get(name):
                    headers[name] = value
            if byte_range:
                headers["Range"] = byte_range
            request = httpx.Request("POST" if form is not None else "GET", dest.copy_with(host=str(addresses[0])),
                                    headers=headers, data=form, extensions={"sni_hostname": host, "timeout": httpx.Timeout(30).as_dict()})
            response = await http.send(request, auth=None, stream=True, follow_redirects=False)
            if not (response.is_redirect and "location" in response.headers and form is None):
                break
            dest = dest.join(response.headers["location"])
            await response.aclose()
            response = None
        yield response if response is not None and response.headers.get("content-encoding", "identity").lower() == "identity" else None
    finally:
        if response is not None:
            await response.aclose()


async def fetch(http: httpx.AsyncClient, url: str, hosts: tuple[str, ...], cap: int, *, form: dict | None = None) -> bytes | None:
    try:
        async with stream(http, url, hosts, form=form) as r:
            if r is None or r.status_code != 200 or int(r.headers.get("content-length", 0)) > cap:
                return None
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                if len(buf) + len(chunk) > cap:
                    return None
                buf.extend(chunk)
            return bytes(buf)
    except (OSError, ValueError, httpx.HTTPError, httpx.InvalidURL):
        return None
