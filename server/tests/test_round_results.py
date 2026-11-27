"""A casting round's results once they went out (Codex's audit): they stand, whatever races them."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

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


@pytest.mark.parametrize("action", ["save", "close", "reopen"])
def test_settings_cannot_undo_a_concurrent_final_send(env, monkeypatch, action):
    con, boss, rid, apps, oid, ids = _round(env)
    body = {"title": "Winter", "closesAt": int(time.time()) + 86400, "departments": []}
    if action == "close":
        body = {"close": True}
    elif action == "reopen":
        body["close"] = False
    other = db.connect(env[1].db_path)

    @contextmanager
    def finish_before_lock(current):
        monkeypatch.setattr(casting, "tx", db.tx)
        casting.send(other, boss, rid, final=True)
        with db.tx(current):
            yield

    monkeypatch.setattr(casting, "tx", finish_before_lock)
    with pytest.raises(logic.ApiError) as no:
        casting.update_round(con, boss, rid, body)
    assert no.value.code == "closed"
    r = con.execute("SELECT * FROM rounds WHERE id = ?", (rid,)).fetchone()
    assert r["status"] == "done" and r["title"] == "Fall" and r["sent_at"]
    assert casting.view(con, boss, oid) is None
    assert all(a["stage"] == "no" and a["sent_at"] for a in con.execute("SELECT * FROM round_apps WHERE round_id = ?", (rid,)))
    other.close()


@pytest.mark.parametrize("stage", ["yes", "no"])
@pytest.mark.parametrize("verdict", ["no", "maybe", "next"])
def test_votes_keep_decisions_until_explicitly_changed(env, stage, verdict):
    con, boss, rid, apps, oid, ids = _round(env)
    app_id = apps[ANN]
    casting.decide(con, boss, app_id, {"stage": stage})
    assert casting.vote(con, boss, app_id, {"verdict": verdict, "stars": 4, "note": "Review"}) == {"stage": stage}
    a = next(a for a in casting.apps(con, boss, rid) if a["id"] == app_id)
    assert a["stage"] == stage and a["votes"][0]["verdict"] == verdict and a["votes"][0]["note"] == "Review"
    casting.decide(con, boss, app_id, {"stage": "new"})
    assert casting.vote(con, boss, app_id, {"verdict": verdict}) == {"stage": verdict}
    assert con.execute("SELECT stage FROM round_apps WHERE id = ?", (app_id,)).fetchone()[0] == verdict


def test_a_no_vote_is_not_a_decision(env):
    """A "no" vote sets the stage, but the next vote still moves it: only a decided "no" stands."""
    con, boss, rid, apps, oid, ids = _round(env)
    app_id = apps[ANN]
    assert casting.vote(con, boss, app_id, {"verdict": "no"}) == {"stage": "no"}
    assert casting.vote(con, boss, app_id, {"verdict": "next"}) == {"stage": "next"}
    assert casting.vote(con, boss, app_id, {"verdict": "no"}) == {"stage": "no"}
    assert casting.vote(con, boss, app_id, {"verdict": "maybe"}) == {"stage": "maybe"}
    casting.decide(con, boss, app_id, {"stage": "no"})
    con.execute("UPDATE round_apps SET updated_at = updated_at - 5 WHERE id = ?", (app_id,))  # decided a moment before the votes
    assert casting.vote(con, boss, app_id, {"verdict": "no"}) == {"stage": "no"}
    assert casting.vote(con, boss, app_id, {"verdict": "next"}) == {"stage": "no"}  # a later "no" vote doesn't undo the decision


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
