"""Bounded HTTPS downloads from the media providers the app uses."""
from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx

TELEGRAM_PAGE = ("t.me",)
TELEGRAM_FILES = ("telesco.pe", "cdn-telegram.org")
TIKTOK_FILES = ("tikwm.com", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokcdn-eu.com", "tiktokv.com")


async def _addresses(host: str) -> list[str]:
    found = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [row[4][0] for row in found]


async def fetch(http: httpx.AsyncClient, url: str, hosts: tuple[str, ...], cap: int, *, form: dict | None = None) -> bytes | None:
    """Resolve and pin each hop. The original host still supplies the Host header and TLS certificate name."""
    try:
        dest = httpx.URL(url)
        for _ in range(5):
            host = dest.host
            if dest.scheme != "https" or dest.port not in (None, 443) or dest.userinfo or not any(
                    host == h or host.endswith("." + h) for h in hosts):
                return None
            addresses = [ipaddress.ip_address(a) for a in await _addresses(host)]
            if not addresses or any(not a.is_global or a.is_multicast or a.is_reserved for a in addresses):
                return None
            # Closing the connection keeps a pooled TLS session for one hostname from serving another at this IP.
            request = httpx.Request("POST" if form is not None else "GET", dest.copy_with(host=str(addresses[0])),
                                    headers={"Host": host, "Connection": "close", "Accept-Encoding": "identity"}, data=form,
                                    extensions={"sni_hostname": host, "timeout": httpx.Timeout(30).as_dict()})
            r = await http.send(request, auth=None, stream=True, follow_redirects=False)
            try:
                if r.is_redirect and "location" in r.headers and form is None:
                    dest = dest.join(r.headers["location"])
                    continue
                if r.status_code != 200 or r.headers.get("content-encoding", "identity").lower() != "identity":
                    return None
                if int(r.headers.get("content-length", 0)) > cap:
                    return None
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    if len(buf) + len(chunk) > cap:
                        return None
                    buf.extend(chunk)
                return bytes(buf)
            finally:
                await r.aclose()
    except (OSError, ValueError, httpx.HTTPError, httpx.InvalidURL):
        pass
    return None
