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
TIMEOUT = 30   # seconds for one step of a request: the name lookup, connecting, each read
DEADLINE = 60  # seconds for a whole fetch however slowly its bytes arrive (a server can trickle a byte per step)


async def _addresses(host: str) -> list[str]:
    found = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [row[4][0] for row in found]


def public(address: str) -> bool:
    """An address on the public internet: never loopback, private, link-local (cloud metadata), shared, multicast or
    reserved, also when written as IPv4 inside IPv6."""
    try:
        a = ipaddress.ip_address(address)
    except ValueError:
        return False
    return a.is_global and not a.is_multicast and not a.is_reserved


def host_allowed(host: str, hosts: tuple[str, ...]) -> bool:
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


def allowed(url: str | httpx.URL, hosts: tuple[str, ...]) -> bool:
    try:
        dest = httpx.URL(url)
        return (dest.scheme == "https" and dest.port in (None, 443) and not dest.userinfo
                and host_allowed(dest.host, hosts))
    except (ValueError, httpx.InvalidURL):
        return False


def typed(r: httpx.Response, types: tuple[str, ...]) -> bool:
    """The response says it is one of these types (or says nothing: the bytes are checked later anyway)."""
    kind = r.headers.get("content-type", "").partition(";")[0].strip().lower()
    return not types or not kind or kind.startswith(types)


@asynccontextmanager
async def stream(http: httpx.AsyncClient, url: str, hosts: tuple[str, ...], *,
                 form: dict | None = None, byte_range: str | None = None, media_headers: dict | None = None):
    """Pin each hop. The original Host and TLS name are preserved for both full files and byte ranges.
    The caller bounds the whole of it in time (fetch: DEADLINE); here each step is bounded."""
    dest = httpx.URL(url)
    response = None
    try:
        for _ in range(5):
            if not allowed(dest, hosts):
                break
            host = dest.host
            async with asyncio.timeout(TIMEOUT):
                addresses = await _addresses(host)
            if not addresses or not all(public(a) for a in addresses):
                break
            headers = {"Host": host, "Connection": "close", "Accept-Encoding": "identity"}
            for name in ("User-Agent", "Referer", "Origin"):
                if value := (media_headers or {}).get(name):
                    headers[name] = value
            if byte_range:
                headers["Range"] = byte_range
            request = httpx.Request("POST" if form is not None else "GET", dest.copy_with(host=str(addresses[0])),
                                    headers=headers, data=form, extensions={"sni_hostname": host, "timeout": httpx.Timeout(TIMEOUT).as_dict()})
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


async def fetch(http: httpx.AsyncClient, url: str, hosts: tuple[str, ...], cap: int, *, form: dict | None = None,
                types: tuple[str, ...] = (), seconds: float = DEADLINE) -> bytes | None:
    """The body if it is 200, at most `cap` bytes as counted on arrival (whatever Content-Length said), of one of
    `types`, and complete within `seconds`; otherwise None."""
    try:
        async with asyncio.timeout(seconds), stream(http, url, hosts, form=form) as r:
            if r is None or r.status_code != 200 or int(r.headers.get("content-length", 0)) > cap or not typed(r, types):
                return None
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                if len(buf) + len(chunk) > cap:
                    return None
                buf.extend(chunk)
            return bytes(buf)
    except (OSError, ValueError, httpx.HTTPError, httpx.InvalidURL):  # TimeoutError is an OSError
        return None
