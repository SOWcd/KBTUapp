"""A casting round's results once they went out (Codex's audit): they stand, whatever races them."""
from __future__ import annotations

import sqlite3
import time

import pytest

from kbtu import casting, db, logic
from test_core import env, login  # noqa: F401  (env: the fixture)

PRES, ANN, BOB = 20, 10, 11


def _round(env, link=None):
    """A club, its President, and a round Ann and Bob applied to: (con, President as a Viewer, round, {tg: application})."""
    c, cfg = env
    ids = {tg: login(c, tg, name)["id"] for tg, name in ((PRES, "pres"), (ANN, "ann"), (BOB, "bob"))}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", True)
    logic.set_role(con, None, ids[PRES], oid, "president", "test")
    boss = logic.Viewer(ids[PRES], "user", True)
    rid = casting.open_round(con, boss, oid, {"title": "Fall", "closesAt": int(time.time()) + 86400, "departments": [], "groupLink": link})["id"]
    apps = {}
    for tg in (ANN, BOB):
        casting.apply(con, logic.Viewer(ids[tg], "user", True), rid, {"departments": [], "answers": {}})
        apps[tg] = con.execute("SELECT id FROM round_apps WHERE user_id = ?", (ids[tg],)).fetchone()[0]
    return con, boss, rid, apps, oid, ids


@pytest.mark.parametrize("call", [lambda con, boss, a: casting.decide(con, boss, a, {"stage": "yes"}),
                                  lambda con, boss, a: casting.vote(con, boss, a, {"verdict": "next"})], ids=["decide", "vote"])
def test_results_sent_mid_decision_stand(env, monkeypatch, call):
    """Results sent between the team's check and its write: never a told "no" turned into something else."""
    con, boss, rid, apps, oid, ids = _round(env)
    casting.decide(con, boss, apps[ANN], {"stage": "no"})
    other = db.connect(env[1].db_path)
    other.execute("PRAGMA busy_timeout = 0")
    real = casting._may

    def racing(*a):  # the moment after the application is read
        monkeypatch.setattr(casting, "_may", real)
        real(*a)
        try:
            casting.send(other, boss, rid, final=False)
        except sqlite3.OperationalError:  # the decision holds the lock: the results come after it
            pass

    monkeypatch.setattr(casting, "_may", racing)
    call(con, boss, apps[ANN])
    casting.send(con, boss, rid, final=False)
    a = con.execute("SELECT stage, sent_at FROM round_apps WHERE id = ?", (apps[ANN],)).fetchone()
    member = con.execute("SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ids[ANN])).fetchone() is not None
    assert not a["sent_at"] or (a["stage"] in ("yes", "no") and member == (a["stage"] == "yes"))


def test_the_group_link_leaves_with_the_member(env):
    """Accepted, then banned or removed from the club: the round no longer hands over the group's invite."""
    con, boss, rid, apps, oid, ids = _round(env, "https://t.me/+AbC_d-12")
    ann = logic.Viewer(ids[ANN], "user", True)
    casting.decide(con, boss, apps[ANN], {"stage": "yes"})
    casting.send(con, boss, rid, final=False)
    assert casting.view(con, ann, oid)["groupLink"]
    con.execute("INSERT INTO org_bans (org_id, user_id, created_at) VALUES (?, ?, 0)", (oid, ids[ANN]))
    assert "groupLink" not in casting.view(con, ann, oid)
    con.execute("DELETE FROM org_bans")
    logic.set_role(con, None, ids[ANN], oid, "none", "test")
    assert "groupLink" not in casting.view(con, ann, oid)


def test_no_interview_after_the_result(env):
    """Told, no time to pick: a seat still ahead goes back to those waiting (one already past stays: who came), the
    app stops offering times, and a late booking is refused."""
    con, boss, rid, apps, oid, ids = _round(env)
    t = int(time.time())
    add = "INSERT INTO round_slots (round_id, starts_at, minutes, capacity, place) VALUES (?, ?, 20, 1, '')"
    ahead, past = con.execute(add, (rid, t + 3600)).lastrowid, con.execute(add, (rid, t - 3600)).lastrowid
    for tg in (ANN, BOB):
        casting.decide(con, boss, apps[tg], {"stage": "next"})
    casting.invite(con, boss, rid)
    ann = logic.Viewer(ids[ANN], "user", True)
    casting.book(con, ann, rid, {"slotId": ahead})
    con.execute("UPDATE round_apps SET slot_id = ? WHERE id = ?", (past, apps[BOB]))
    casting.decide(con, boss, apps[ANN], {"stage": "no"})
    casting.decide(con, boss, apps[BOB], {"stage": "yes"})
    casting.send(con, boss, rid, final=False)
    slot = lambda tg: con.execute("SELECT slot_id FROM round_apps WHERE id = ?", (apps[tg],)).fetchone()[0]  # noqa: E731
    assert slot(ANN) is None and slot(BOB) == past
    assert not casting.view(con, ann, oid)["mine"]["invited"]
    with pytest.raises(logic.ApiError) as no:
        casting.book(con, ann, rid, {"slotId": ahead})
    assert no.value.code == "closed" and slot(ANN) is None
