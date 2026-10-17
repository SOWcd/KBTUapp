"""KBTU's psychological service: its nearest free consultation, read off the service's public Microsoft Bookings page
(no sign-in; the same calls the page makes), for the row in Me (owner, Oct 15). Nothing about the student is sent;
booking stays on their page. The page answers in ~20 s, so the answer is kept a while and refreshed in the background:
a request never waits for Bookings."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

BASE = "https://outlook.office365.com/BookingsService/api/V1/bookingBusinessesc2/Bookings7@kbtu.kz"
FRESH = 15 * 60  # seconds an answer is good for
LEAD = timedelta(hours=2)  # the page's minimumLeadTime
LONG = timedelta(minutes=50)  # a consultation
log = logging.getLogger(__name__)

_cache: dict = {"at": 0.0, "next": None}
_busy = False


def first_slot(staff: list[dict], now: datetime) -> datetime | None:
    """The earliest hour (slots start on the hour) at least LEAD from now that fits a consultation in someone's
    AVAILABLE window. `staff`: GetStaffAvailability's staffAvailabilityResponse, asked in UTC."""
    best = None
    for s in staff:
        for i in s.get("availabilityItems", []):
            if i.get("status") != "BOOKINGSAVAILABILITYSTATUS_AVAILABLE":
                continue
            a = datetime.fromisoformat(i["startDateTime"]["dateTime"]).replace(tzinfo=timezone.utc)
            b = datetime.fromisoformat(i["endDateTime"]["dateTime"]).replace(tzinfo=timezone.utc)
            a = max(a, now + LEAD)
            if a.minute or a.second or a.microsecond:
                a = a.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            if a + LONG <= b and (best is None or a < best):
                best = a
    return best


async def _refresh() -> None:
    global _busy
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            svc = (await http.post(f"{BASE}/services", json={})).json()["service"][0]
            now = datetime.now(timezone.utc)
            fmt = "%Y-%m-%dT%H:%M:%S"
            r = await http.post(f"{BASE}/GetStaffAvailability", json={
                "serviceId": svc["serviceId"], "staffIds": svc["staffMemberIds"],
                "startDateTime": {"dateTime": now.strftime(fmt), "timeZone": "UTC"},
                "endDateTime": {"dateTime": (now + timedelta(days=11)).strftime(fmt), "timeZone": "UTC"}})
            slot = first_slot(r.json()["staffAvailabilityResponse"], now)
        _cache.update(at=time.time(), next=int(slot.timestamp()) if slot else None)
    except Exception as e:  # their page changed or is down: the row just shows no time
        log.warning("psych: %s", e)
        _cache["at"] = time.time() - FRESH + 120  # try again in two minutes
    finally:
        _busy = False


def nearest() -> int | None:
    """The cached nearest slot (unix seconds) or None; a stale cache starts a refresh and answers what it has."""
    global _busy
    if time.time() - _cache["at"] > FRESH and not _busy:
        _busy = True
        asyncio.get_running_loop().create_task(_refresh())
    return _cache["next"] if _cache["next"] and _cache["next"] > time.time() + LEAD.total_seconds() else None


if __name__ == "__main__":  # the slot rule's check
    U = lambda s: {"dateTime": s, "timeZone": "UTC"}
    av = lambda a, b: {"status": "BOOKINGSAVAILABILITYSTATUS_AVAILABLE", "startDateTime": U(a), "endDateTime": U(b)}
    now = datetime(2026, 10, 15, 3, 30, tzinfo=timezone.utc)
    staff = [{"availabilityItems": [av("2026-10-15T04:50:00", "2026-10-15T05:00:00"),  # ten minutes: no
                                    av("2026-10-15T04:00:00", "2026-10-15T06:00:00"),  # 05:30 lead -> 06:00: no room
                                    {**av("2026-10-15T07:00:00", "2026-10-15T08:00:00"), "status": "BOOKINGSAVAILABILITYSTATUS_BUSY"}]},
             {"availabilityItems": [av("2026-10-15T09:00:00", "2026-10-15T10:00:00")]}]
    assert first_slot(staff, now) == datetime(2026, 10, 15, 9, tzinfo=timezone.utc)
    assert first_slot([], now) is None
    print("ok")
