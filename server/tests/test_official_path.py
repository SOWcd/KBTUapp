"""The Ascent (logic/clubs.py, official_path): a checklist in any order that locks nothing (a ready profile, a round
that took someone, a Telegram channel, a collab with an official club; the top: all of them and two events with
outside guests (5 at each, 10 different), an official club's tools without the ✓, the owner told once). At the top the President or a Vice may ask for the ✓, once, again 30 days
after a no; only the admin decides; Undo takes it back."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

ADMIN, PRES, VICE, HEAD, A, B, C, D, E = 60, 61, 62, 63, 64, 65, 66, 67, 68
DAY = 86400


def _setup(env):
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({ADMIN}))))
    ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (ADMIN, PRES, VICE, HEAD, A, B, C, D, E)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", False)
    for tg, role in ((PRES, "president"), (VICE, "vice"), (HEAD, "head")):
        logic.set_role(con, None, ids[tg], oid, role, "test")
    return c, con, ids, oid


def _path(c, oid, who=PRES):
    return c.get(f"/api/orgs/{oid}/official-path", headers=tma(who)).json()["path"]


def _steps(c, oid, who=PRES):
    return _path(c, oid, who)["steps"]


def _members(con, ids, oid, *tgs):
    for tg in tgs:
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (oid, ids[tg]))


def _profile(con, oid):
    fid = con.execute("INSERT INTO files (sha256, kind, mime, bytes, path, created_at) VALUES ('l', 'org_logo', 'image/webp', 1, 'ab/l', 0)").lastrowid
    con.execute("UPDATE orgs SET logo_file_id = ?, description = 'We play chess every Friday.' WHERE id = ?", (fid, oid))


def _channel(con, oid):
    con.execute("INSERT INTO chats (title, kind, url, org_id, created_at) VALUES ('Chess', 'channel', 'https://t.me/kbtu_chess', ?, 0)", (oid,))


def _round(con, ids, oid, stage="yes"):
    rid = con.execute("INSERT INTO rounds (org_id, title, closes_at, status, created_at) VALUES (?, 'Fall', 0, 'done', 0)", (oid,)).lastrowid
    con.execute("INSERT INTO round_apps (round_id, user_id, departments, answers, stage, created_at, updated_at) VALUES (?, ?, '[]', '{}', ?, 0, 0)",
                (rid, ids[E], stage))


def _event(con, oid, ago=DAY):
    t = logic.now()
    return con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, ends_at, emoji, color, created_at, updated_at)
        VALUES (?, 'published', 'Blitz', '305', ?, ?, 'crown_3d', '#3B6BFF', 0, 0)""", (oid, t - ago, t - ago + 3600)).lastrowid


def _came(con, eid, uid, manual=0):
    con.execute("""INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at, checked_in_at, checkin_manual)
        VALUES (?, ?, 'going', ?, 0, 0, ?, ?)""", (eid, uid, f"t{eid}-{uid}", logic.now(), manual))


def _guests(con, n):
    """n students from outside the club, users only (a door scan needs no more)."""
    return [con.execute("INSERT INTO users (tg_id, created_at, seen_at) VALUES (?, 0, 0)", (9000 + i,)).lastrowid for i in range(n)]


def _all_done(con, ids, oid):
    """Every level, the quick way (each one's own test is below)."""
    con.execute("UPDATE org_members SET joined_at = 0 WHERE org_id = ?", (oid,))
    _members(con, ids, oid, D, E)
    _profile(con, oid)
    _round(con, ids, oid)
    _channel(con, oid)
    off = logic.create_org(con, None, "Debate", "DB", "crown_3d", True)
    g = _guests(con, 10)
    for part in (g[:5], g[5:]):
        eid = _event(con, oid)
        for u in part:
            _came(con, eid, u)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (eid, off))


def test_each_level(env):
    c, con, ids, oid = _setup(env)
    assert _steps(c, oid) == dict.fromkeys(logic.PATH_STEPS, False)
    assert c.get(f"/api/orgs/{oid}/official-path", headers=tma(A)).status_code == 403  # not in the club
    # 1. the profile: a logo, a description of 10+ and 5 members in the app (a banned one doesn't count)
    _profile(con, oid)
    con.execute("UPDATE orgs SET description = 'hi' WHERE id = ?", (oid,))
    _members(con, ids, oid, D, E)
    assert not _steps(c, oid)["profile"] and _path(c, oid)["members"] == 5
    con.execute("UPDATE orgs SET description = 'We play chess every Friday.' WHERE id = ?", (oid,))
    assert _steps(c, oid)["profile"]
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids[HEAD],))
    assert not _steps(c, oid)["profile"]
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ids[HEAD],))
    con.execute("UPDATE org_members SET joined_at = ? WHERE org_id = ?", (logic.now() - 4 * DAY, oid))  # in the club before its events below
    # 2. a round with results out that took someone
    _round(con, ids, oid, "no")
    assert not _steps(c, oid)["round"]
    con.execute("UPDATE round_apps SET stage = 'yes'")
    assert _steps(c, oid)["round"]
    # any order: a round done counts without the profile
    con.execute("UPDATE orgs SET description = '' WHERE id = ?", (oid,))
    assert _steps(c, oid) == {**dict.fromkeys(logic.PATH_STEPS, False), "round": True}
    con.execute("UPDATE orgs SET description = 'We play chess every Friday.' WHERE id = ?", (oid,))
    # a Telegram channel linked (a group isn't one)
    con.execute("INSERT INTO chats (title, kind, url, org_id, created_at) VALUES ('Chat', 'group', 'https://t.me/kbtu_chess_chat', ?, 0)", (oid,))
    assert not _steps(c, oid)["channel"]
    _channel(con, oid)
    assert _steps(c, oid)["channel"]
    # 3. a collab: an accepted official co-host (pending or unofficial doesn't do)
    later = _event(con, oid, ago=-DAY)
    other = logic.create_org(con, None, "Debate", "DB", "crown_3d", False)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'pending', 0)", (later, other))
    assert not _steps(c, oid)["collab"]
    con.execute("UPDATE event_cohosts SET status = 'accepted'")
    assert not _steps(c, oid)["collab"]
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (other,))
    assert _steps(c, oid)["collab"]
    con.execute("DELETE FROM event_cohosts")  # the other way round: we co-host an official club's event
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (_event(con, other), oid))
    assert _steps(c, oid)["collab"]
    # 4. the top: two events over, 5 outside guests scanned at each and 10 different across the two (owner, Nov 10). Not
    # guests: the team, a check-in by hand, a member from before, a former member, the creator, a helper, a co-host's people
    g = _guests(con, 12)
    eid = _event(con, oid)
    for tg in (PRES, VICE, HEAD):
        _came(con, eid, ids[tg])
    _came(con, eid, ids[B], manual=1)
    for u in g[:4]:
        _came(con, eid, u)
    for u in g[:5]:
        _came(con, later, u)  # still to come
    _came(con, eid, ids[D])  # D joined the club before the event: a member, not a guest
    con.execute("UPDATE org_members SET joined_at = 0 WHERE user_id = ?", (ids[D],))
    assert _path(c, oid)["events"] == 0
    con.execute("INSERT INTO org_history (user_id, org_id, role, since, until) VALUES (?, ?, 'member', 0, 1)", (g[4], oid))  # left long ago
    con.execute("UPDATE events SET created_by = ? WHERE id = ?", (g[5], eid))
    con.execute("INSERT INTO event_crew (event_id, user_id, org_id, kind, created_at) VALUES (?, ?, ?, 'scan', 0)", (eid, g[6], oid))
    co = logic.create_org(con, None, "Go", "GO", "crown_3d", False)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (eid, co))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (co, g[7]))
    con.execute("UPDATE org_history SET since = 0 WHERE user_id = ?", (g[7],))
    for u in g[4:8]:
        _came(con, eid, u)
    assert _path(c, oid)["events"] == 0
    con.execute("UPDATE org_members SET joined_at = ? WHERE user_id = ?", (logic.now(), ids[D]))  # joined after: counts
    con.execute("UPDATE org_history SET since = ? WHERE user_id = ? AND org_id = ?", (logic.now(), ids[D], oid))
    p = _path(c, oid)
    assert p["events"] == 1 and p["guests"] == 5 and not p["steps"]["top"]
    two = _event(con, oid)
    for u in (ids[D], *g[:4]):
        _came(con, two, u)  # the same five again: two events, but 5 different, not 10
    p = _path(c, oid)
    assert p["events"] == 2 and p["guests"] == 5 and not p["steps"]["top"]
    for u in g[8:12]:
        _came(con, two, u)
    assert _path(c, oid)["guests"] == 9 and not _steps(c, oid)["top"]
    _came(con, two, ids[C])
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'club_top'").fetchone()[0] == 0
    assert _steps(c, oid)["top"]
    # the top is kept: the founder hears once, the clubs list shows it, losing a member takes nothing back
    assert con.execute("SELECT top_at FROM orgs WHERE id = ?", (oid,)).fetchone()[0]
    _steps(c, oid)
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'club_top'").fetchone()[0] == 0  # no founder in this test
    con.execute("DELETE FROM org_members WHERE user_id = ?", (ids[E],))
    assert _steps(c, oid) == dict.fromkeys(logic.PATH_STEPS, True)
    assert logic.path_top(con, oid) and not logic.path_top(con, other)
    assert next(o for o in c.get("/api/orgs", headers=tma(A)).json() if o["id"] == oid)["top"] is True
    # an official club sees no path
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (oid,))
    assert _path(c, oid) is None


def test_founder_told_once(env):
    c, con, ids, oid = _setup(env)
    con.execute("UPDATE users SET is_founder = 1, role = 'admin' WHERE id = ?", (ids[ADMIN],))
    _all_done(con, ids, oid)
    _steps(c, oid); _steps(c, oid)
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'club_top'").fetchall()
    assert [r["user_id"] for r in told] == [ids[ADMIN]] and told[0]["ref"] == f"top:{oid}"
    text, _, start = bot._render(con, dict(told[0]))
    assert "Chess" in text and "lanyard" in text and start == f"cl_{oid}"


def test_nothing_locked(env):
    """The path locks nothing (owner, Nov 6): a fresh initiative opens a round and makes an event; a price is an official
    club's tool, and the top's."""
    c, con, ids, oid = _setup(env)
    rnd = {"title": "Fall", "closesAt": logic.now() + 7 * DAY, "departments": []}
    ev = {"title": "Blitz", "place": "305", "startsAt": logic.now() + 2 * DAY, "emoji": "crown_3d", "color": "#3B6BFF"}
    assert c.post(f"/api/orgs/{oid}/round", headers=tma(PRES), json=rnd).status_code == 200
    assert c.post(f"/api/orgs/{oid}/events", headers=tma(PRES), json=ev).status_code == 200
    paid = {**ev, "price": 1000, "payToName": "Chess Club", "payPhone": "87011234567"}
    assert c.post(f"/api/orgs/{oid}/events", headers=tma(PRES), json=paid).status_code == 403
    con.execute("UPDATE orgs SET top_at = 1 WHERE id = ?", (oid,))
    assert c.post(f"/api/orgs/{oid}/events", headers=tma(PRES), json=paid).status_code == 200


def test_stories_open_at_collab(env):
    """Stories (club posts) are an official club's, and an initiative's from the Ascent's collab step on (owner, Nov 7):
    below it a 403 the composer names, the old posts stay, and the step opens them by itself."""
    c, con, ids, oid = _setup(env)
    post = {"title": "Walked", "body": "", "tag": "important"}
    con.execute("INSERT INTO posts (org_id, author_id, audience, title, body, created_at) VALUES (?, ?, 'public', 'Old', '', 0)", (oid, ids[PRES]))

    def mine():
        return next(m for m in c.get("/api/me", headers=tma(PRES)).json()["memberships"] if m["org"]["id"] == oid)
    assert mine()["storiesLocked"] is True
    r = c.post(f"/api/orgs/{oid}/posts", headers=tma(PRES), json=post)
    assert r.status_code == 403 and "ascent" in r.text
    assert con.execute("SELECT COUNT(*) FROM posts WHERE org_id = ?", (oid,)).fetchone()[0] == 1  # the old one kept
    off = logic.create_org(con, None, "Debate", "DB", "crown_3d", True)
    con.execute("INSERT INTO event_cohosts (event_id, org_id, status, created_at) VALUES (?, ?, 'accepted', 0)", (_event(con, oid, ago=-DAY), off))
    assert "storiesLocked" not in mine()
    assert c.post(f"/api/orgs/{oid}/posts", headers=tma(PRES), json=post).status_code == 200
    # an initiative at the top, and an official club, write as before
    con.execute("DELETE FROM event_cohosts")
    con.execute("UPDATE orgs SET top_at = 1 WHERE id = ?", (oid,))
    assert c.post(f"/api/orgs/{oid}/posts", headers=tma(PRES), json=post).status_code == 200
    con.execute("UPDATE orgs SET top_at = NULL, official = 1 WHERE id = ?", (oid,))
    assert c.post(f"/api/orgs/{oid}/posts", headers=tma(PRES), json=post).status_code == 200


def test_request_lifecycle(env, monkeypatch):
    c, con, ids, oid = _setup(env)
    ask = lambda who=PRES: c.post(f"/api/orgs/{oid}/official-path", headers=tma(who))  # noqa: E731
    assert ask().status_code == 400  # not at the top
    _all_done(con, ids, oid)
    _steps(c, oid)  # the top, seen in Studio
    assert ask(HEAD).status_code == 403 and ask(A).status_code == 403  # the President or a Vice only
    r = ask(VICE)
    assert r.status_code == 200 and r.json()["path"]["request"]["status"] == "pending"
    assert ask().status_code == 409  # one at a time
    rid = r.json()["path"]["request"]["id"]
    told = con.execute("SELECT u.tg_id, b.ref FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'club_path'").fetchall()
    assert [tuple(t) for t in told] == [(ADMIN, f"opath:{rid}")]
    row = dict(con.execute("SELECT * FROM bot_outbox WHERE kind = 'club_path'").fetchone()) | {"lang": "en"}
    text, _, start = bot._render(con, row)
    assert "Chess" in text and start == "capps"
    # only the admin decides; it's in his Inbox
    decide = lambda who=ADMIN, **b: c.post(f"/api/admin/official-requests/{rid}", headers=tma(who), json=b)  # noqa: E731
    assert decide(PRES, approve=True).status_code == 403
    inbox = c.get("/api/admin/inbox", headers=tma(ADMIN)).json()
    assert [x["key"] for x in inbox["items"] if x["kind"] == "opath"] == [f"opath:{rid}"]
    assert decide(approve=False, reason="x").status_code == 400  # a no needs its reason
    assert decide(approve=False, reason="Not yet, come in spring").status_code == 200
    p = _path(c, oid, HEAD)
    assert p["request"]["status"] == "rejected" and p["request"]["reason"] == "Not yet, come in spring"
    assert decide(approve=True).status_code == 409  # decided already
    assert ask().status_code == 429  # 30 days after a no
    # Undo the no: waiting again; then a yes makes it official, its President told after the Undo's minute
    done = c.get("/api/admin/inbox", headers=tma(ADMIN)).json()["done"]
    no = next(d for d in done if d["action"] == "opath_no")
    assert no["undo"] and no["text"].startswith("Chess")
    assert c.post(f"/api/admin/done/{no['id']}/undo", headers=tma(ADMIN)).status_code in (200, 204)
    assert _path(c, oid)["request"]["status"] == "pending"
    assert decide(approve=True).status_code == 200
    assert con.execute("SELECT official FROM orgs WHERE id = ?", (oid,)).fetchone()[0] == 1
    assert _path(c, oid) is None
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'club_official' AND sent_at IS NULL").fetchone()[0] == 1
    # Undo the yes: the ✓ back off, the message unsent, the request waits
    yes = next(d for d in c.get("/api/admin/inbox", headers=tma(ADMIN)).json()["done"] if d["action"] == "opath_yes")
    assert c.post(f"/api/admin/done/{yes['id']}/undo", headers=tma(ADMIN)).status_code in (200, 204)
    assert con.execute("SELECT official FROM orgs WHERE id = ?", (oid,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'club_official'").fetchone()[0] == 0
    assert _path(c, oid)["request"]["status"] == "pending"
    # a no again, then 31 days later the club may ask again
    assert decide(approve=False, reason="Not yet, come in spring").status_code == 200
    t = logic.now() + 31 * DAY
    monkeypatch.setattr(logic.core, "now", lambda: t)
    assert ask().status_code == 200
