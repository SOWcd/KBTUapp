"""What the server's tests share: a signed Telegram user (tma), the app on a fresh database (env), a confirmed KBTU
student (login), the rules' clock (set_clock), an account deleted at once (delete_now), and a club, the forum and the
check-in screen set up for a test (_club_runs, _board_on, _paired, _csv). test_core.py re-exports all of it, so
`from test_core import env, login, tma` keeps working."""
from __future__ import annotations

import os
import shutil
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kbtu import auth, chores, config, db, logic, receipt, app as server


BOT = "123:" + "test" * 9


def delete_now(c, cfg, h: dict) -> None:
    """"Delete my account", and the week gone by: the bot's round deletes it."""
    assert c.post("/api/me/delete", headers=h).status_code == 200
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET delete_at = 0 WHERE delete_at IS NOT NULL")
    chores.purge(cfg, con)
    con.close()


def tma(uid: int, first: str = "Test") -> dict:
    return {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": first}, BOT)}


@pytest.fixture
def env(tmp_path, monkeypatch, _schema_db):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><head><title>app</title></head></html>")
    (dist / "assets" / "a.js").write_text("1")
    (dist / "sw.js").write_text("1")
    (dist / "map" / "u1").mkdir(parents=True)
    (dist / "emoji").mkdir()
    shutil.copy(Path(__file__).parents[2] / "web/public/emoji/party_popper_3d.webp", dist / "emoji")
    (dist / "map" / "u1" / "o.webp").write_bytes(b"RIFF")
    cfg = config.Config(bot_token=BOT, token_key=os.urandom(32), db_path=str(tmp_path / "t.db"), web_dist=str(dist), background=False, seed=False)

    monkeypatch.setattr(logic.clubs, "CLUB_MIN", 1)  # the registry's size bar stays out of the other tests (test_club_solo sets it)

    monkeypatch.setattr(logic.clubs, "CLUB_QUIET", 1 << 40)  # and its activity bar
    monkeypatch.setattr(logic.profiles, "FIRST_N", 0)  # "First 500" stays out of the other tests' outboxes (test_first_fifty turns it on)
    monkeypatch.setattr(receipt, "read", lambda im: None)  # no OCR: tests don't depend on Tesseract (test_receipt_reading fakes it)
    shutil.copy(_schema_db, cfg.db_path)
    DB[:] = [cfg.db_path]
    client = TestClient(server.create(cfg))
    return client, cfg


DB: list[str] = []  # the env's database (login() writes students straight into it)


def set_clock(monkeypatch, fake) -> None:
    """The rules' clock (logic.core.now, which every logic module reads), and logic.now the tests read too."""
    monkeypatch.setattr(logic.core, "now", fake)
    monkeypatch.setattr(logic, "now", fake)


INTAKE = time.gmtime(time.time() + 5 * 3600).tm_year - (time.gmtime(time.time() + 5 * 3600).tm_mon < 9)  # this academic year's first-years entered then (Almaty)


def login(c, uid: int, name: str):
    """A confirmed KBTU student "<name>": student ID 24B<name>, <Name> Testov, year 2, SITE, a Monday Calculus class.
    Written into the database as the KBTU sign-in did (the portal-password one is gone since Oct 19)."""
    me = c.get("/api/me", headers=tma(uid, name.title())).json()
    con = db.connect(DB[0])
    with db.tx(con):
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, school, consent_version, consent_at,
                verified_at, synced_at) VALUES (?, ?, ?, 'Testov', 2, 'SITE', '1', ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET student_id = excluded.student_id, first_name = excluded.first_name, manual = 0""",
                    (me["id"], "24B" + name, name.title(), *[logic.now()] * 3))
        logic.save_schedule(con, me["id"], [types.SimpleNamespace(weekday=1, begins="09:00", ends="09:50", subject="Calculus",
                                                                  code="MATH101", kind="lecture", room="305", teacher=None)])
    con.close()
    r = c.get("/api/me", headers=tma(uid))
    assert r.status_code == 200, r.text
    return r.json()


def _board_on(c, cfg) -> None:
    """The student forum's routes open (BOARD=1) for this app; the policy version stays the env's (sign-ins keep working)."""
    import dataclasses
    c.app.state.cfg = dataclasses.replace(cfg, board="all")
    c.app.state.policy = "1"  # the version login() writes: everyone here agreed to the policy in force


def _club_runs(c, con, uid: int, name: str, slug: str = "vol") -> int:
    """A club whose Head (uid) runs its events, so its check-in sessions too."""
    login(c, uid, name)
    oid = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES (?, 'club', ?, 'V', 'trophy_3d', 0)",
                      (slug, slug.title())).lastrowid
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', 0)",
                (oid, c.get("/api/me", headers=tma(uid)).json()["id"]))
    return oid


def _paired(c, uid: int, sid: int | None = None) -> dict:
    """A laptop's /show paired by the organizer uid: its header for what to show."""
    scr = c.post("/api/screen/pair").json()
    assert c.post("/api/screens/bind", headers=tma(uid), json={"code": scr["code"], "session": sid}).status_code == 200
    return {"X-Screen": scr["secret"]}


def _csv(c, uid: int, sid: int) -> str:
    return c.get(c.post(f"/api/screens/{sid}/csv", headers=tma(uid)).json()["url"]).text.lstrip("\ufeff")
