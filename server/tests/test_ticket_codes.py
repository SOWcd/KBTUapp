"""Ticket codes are 4 characters, unique within their event (owner, Nov 8): stored as '<event id>-<code>'; the door
finds a code in its own event only."""
from __future__ import annotations

import itertools
import re
import time

from kbtu import db
from kbtu.logic import seats
from test_core import env, login, tma  # noqa: F401  (env is a fixture)


def _setup(c, cfg):
    """IT Club (tg 20 its president), two events starting in 10 minutes (the door open), tg 10 and 11 students."""
    for tg, name in ((20, "pres"), (10, "ali"), (11, "bob")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    start = int(time.time()) + 600
    eids = []
    for title in ("Case", "Talk"):
        body = {"seats": None, "title": title, "place": "Hall", "startsAt": start, "endsAt": start + 7200, "emoji": "laptop_3d", "color": "#3B6BFF"}
        eid = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()["id"]
        assert c.post(f"/api/events/{eid}/publish", headers=tma(20)).status_code == 200
        eids.append(eid)
    return con, eids


def test_codes_per_event(env, monkeypatch):
    c, cfg = env
    con, (a, b) = _setup(c, cfg)
    code = c.post(f"/api/events/{a}/registration", headers=tma(10), json={}).json()["my"]["ticketCode"]
    assert re.fullmatch(r"[2-9A-HJKMNP-Z]{4}", code)  # no 0/O, 1/I/L
    assert con.execute("SELECT ticket_code FROM registrations WHERE event_id = ?", (a,)).fetchone()[0] == f"{a}-{code}"
    # the same code is free in another event; taken in its own, a new one is drawn
    con.execute("UPDATE registrations SET ticket_code = ? WHERE event_id = ?", (f"{a}-2222", a))
    monkeypatch.setattr(seats.secrets, "choice", lambda s: "2")
    assert seats._ticket_code(con, b) == f"{b}-2222"
    draws = itertools.chain("2222", itertools.repeat("3"))
    monkeypatch.setattr(seats.secrets, "choice", lambda s: next(draws))
    assert seats._ticket_code(con, a) == f"{a}-3333"


def test_door_reads_own_event_only(env):
    c, cfg = env
    con, (a, b) = _setup(c, cfg)
    code = c.post(f"/api/events/{a}/registration", headers=tma(10), json={}).json()["my"]["ticketCode"]
    scan = lambda eid, raw: c.post(f"/api/events/{eid}/checkin", headers=tma(20), json={"code": raw}).json()
    assert scan(b, "KBTU" + code)["result"] == "not_found"  # another event's code means nothing here
    assert scan(b, f"{a}-{code}")["result"] == "not_found"  # nor its stored form
    assert scan(a, "KBTU" + code)["result"] == "ok"  # the QR
    assert scan(a, f" {code[:2].lower()} - {code[2:].lower()} ")["result"] == "already"  # typed by hand
