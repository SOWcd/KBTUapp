"""Clubs: join requests, the admin's club list, Studio's team (roles, tags, departments), news, the registry, short links."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kbtu import auth, bot, db, logic, app as server, texts
from test_core import BOT, INTAKE, env, login, tma  # noqa: F401  (env: the fixture)


def test_join_requests(env):
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    P, A = tma(20, "Pres"), tma(21, "Ali")
    pings = lambda: con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ? AND kind = 'join_request'", (pres["id"],)).fetchone()[0]

    assert c.get("/api/orgs/1", headers=A).json()["recruiting"] is True          # open unless the club closes it
    assert c.post("/api/orgs/1/join-requests", headers=tma(22, "Guest")).status_code == 401
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["myRequest"] == "pending"
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["myRequest"] == "pending" and pings() == 1  # twice = once
    assert c.get("/api/orgs/1/join-requests", headers=A).status_code == 403      # the inbox is Vice+
    inbox = c.get("/api/orgs/1/join-requests", headers=P).json()
    assert [(r["fullName"], r["course"]) for r in inbox] == [("Testov Ali", 2)]
    ping = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'join_request'").fetchone()
    assert bot._render(con, ping)[2] == "jr_1"

    # withdrawn: the club's ping goes nowhere; asking again the same day doesn't ping twice
    assert c.delete("/api/orgs/1/join-requests/mine", headers=A).json()["myRequest"] is None
    assert bot._render(con, ping) is None
    c.post("/api/orgs/1/join-requests", headers=A)
    assert pings() == 1

    # declined: the bot tells, and no new application for 30 days
    first = c.get("/api/orgs/1/join-requests", headers=P).json()[0]["id"]
    assert c.post(f"/api/join-requests/{first}/reject", headers=P).status_code == 204
    assert c.post(f"/api/join-requests/{first}/accept", headers=P).status_code == 409   # already answered
    assert c.get("/api/orgs/1", headers=A).json()["myRequest"] == "rejected"
    assert c.post("/api/orgs/1/join-requests", headers=A).status_code == 429
    con.execute("UPDATE join_requests SET decided_at = decided_at - 31 * 86400")

    # closed: nobody can apply
    assert c.patch("/api/orgs/1", headers=A, json={"recruiting": False}).status_code == 403
    assert c.patch("/api/orgs/1", headers=P, json={"recruiting": False}).json()["recruiting"] is False
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["error"] == "closed"
    c.patch("/api/orgs/1", headers=P, json={"recruiting": True})

    # accepted: a member at once, the bot tells
    c.post("/api/orgs/1/join-requests", headers=A)
    second = c.get("/api/orgs/1/join-requests", headers=P).json()[0]["id"]
    assert c.post(f"/api/join-requests/{second}/accept", headers=P).status_code == 204
    assert [(m["org"]["id"], m["role"]) for m in c.get("/api/me", headers=A).json()["memberships"]] == [(1, "member")]
    assert c.post("/api/orgs/1/join-requests", headers=A).json()["error"] == "conflict"
    told = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'join_decided' ORDER BY id").fetchall()
    assert [r["ref"] for r in told] == [f"jr:{first}:no", f"jr:{second}:yes"]
    assert [bot._render(con, r)[1:] for r in told] == [(None, "cl_1"), (texts.bot_message("ru", "join_yes", org="")[1], "cl_1")]


def test_admin_clubs(env):
    """The pilot's admin panel (SPEC §2): the admin creates a club and gives it a president by @username or Telegram ID;
    a new president moves the old one to vice; nobody else can do any of it."""
    import dataclasses
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({20}))))
    who = lambda uid, first, username: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": first, "username": username}, BOT)}
    A, P = who(20, "Owner", "owner"), who(21, "Pres", "pres_kbtu")
    c.get("/api/me", headers=A)
    login(c, 21, "pres")
    assert c.get("/api/admin/orgs", headers=P).status_code == 403
    assert c.post("/api/admin/orgs", headers=P, json={"name": "Chess", "short": "C", "emoji": "trophy_3d"}).status_code == 403
    assert c.post("/api/admin/orgs", headers=A, json={"name": "X", "short": "X", "emoji": "trophy_3d"}).status_code == 400

    club = c.post("/api/admin/orgs", headers=A, json={"name": "Chess Club", "short": "ch", "emoji": "trophy_3d", "official": True}).json()
    assert (club["short"], club["official"], club["slug"], club["team"], club["members"]) == ("CH", True, "chess", [], 0)
    put = lambda body: c.put(f"/api/admin/orgs/{club['id']}/role", headers=A, json=body)
    assert put({"who": "@nobody", "role": "president"}).json()["message"] == "who"   # never opened the app
    assert put({"who": "@pres_kbtu", "role": "boss"}).status_code == 400
    team = put({"who": "@PRES_kbtu", "role": "president"}).json()["team"]
    assert [(m["username"], m["role"], m["student"]) for m in team] == [("pres_kbtu", "president", True)]
    assert [(m["org"]["id"], m["role"]) for m in c.get("/api/me", headers=P).json()["memberships"]] == [(club["id"], "president")]

    c.get("/api/me", headers=who(22, "Next", "next_one"))                              # a guest so far
    team = put({"who": "22", "role": "president"}).json()["team"]                      # by Telegram ID
    assert [(m["username"], m["role"], m["student"]) for m in team] == [("next_one", "president", False), ("pres_kbtu", "vice", True)]
    assert put({"who": "@pres_kbtu", "role": "none"}).json()["members"] == 1
    # every step was written down by itself (org_history's triggers): President, then Vice, then out; a role held under
    # a day doesn't show, so the test moves the clock back two days
    con = db.connect(cfg.db_path)
    pid = c.get("/api/me", headers=P).json()["id"]
    assert [tuple(r) for r in con.execute("SELECT role, until IS NULL FROM org_history WHERE user_id = ? ORDER BY id", (pid,))] == [("president", 0), ("vice", 0)]
    con.execute("UPDATE org_history SET since = since - 2 * 86400 WHERE user_id = ?", (pid,))
    past = c.get(f"/api/users/{pid}", headers=P).json()["past"]
    assert [(x["org"]["id"], x["role"]) for x in past] == [(club["id"], None), (club["id"], None)]  # the role: to the club's team only
    assert [o["id"] for o in c.get("/api/admin/orgs", headers=A).json()] == [club["id"]]
    # a row of the team acts by the app's user id: the @username it showed may be someone else's by now. Only on
    # someone in this club (the one removed above is nobody's row), and written down like any role change
    nid = team[0]["id"]
    con.execute("UPDATE users SET tg_username = 'next_one' WHERE id = ?", (pid,))
    con.execute("UPDATE users SET tg_username = 'renamed' WHERE id = ?", (nid,))
    team = put({"userId": nid, "role": "head"}).json()["team"]
    assert [(m["id"], m["username"], m["role"]) for m in team] == [(nid, "renamed", "head")]
    assert put({"userId": pid, "role": "head"}).json()["message"] == "who" and put({"userId": True, "role": "head"}).status_code == 404
    assert put({"userId": str(nid), "role": "head"}).status_code == 404 and put({"userId": nid, "role": "boss"}).status_code == 400
    assert json.loads(con.execute("SELECT data FROM audit_log WHERE action = 'role_change' AND target = ? ORDER BY id DESC", (f"user:{nid}",)).fetchone()[0])["role"] == "head"
    assert put({"userId": nid, "role": "president"}).json()["team"][0]["role"] == "president"
    # hide, never delete: gone for everyone but the admin's list, and back with one more tap
    hide = lambda on, h=A: c.put(f"/api/admin/orgs/{club['id']}/hidden", headers=h, json={"hidden": on})
    assert hide(True, P).status_code == 403
    assert hide(True).json()["hidden"] is True
    assert c.get(f"/api/orgs/{club['id']}", headers=P).status_code == 404 and c.get(f"/api/orgs/{club['id']}", headers=A).status_code == 200
    assert club["id"] not in [o["id"] for o in c.get("/api/orgs", headers=P).json()]
    assert hide(False).json()["hidden"] is False and c.get(f"/api/orgs/{club['id']}", headers=P).status_code == 200
    # schools come from KBTU's site (seed_schools), never made by hand; their President by the same link
    for kind in ("office", "school"):
        assert c.post("/api/admin/orgs", headers=A, json={"name": "School of IT", "short": "IT", "emoji": "laptop_3d", "kind": kind}).status_code == 400
    con = db.connect(cfg.db_path)
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    school = con.execute("SELECT id, official FROM orgs WHERE slug = 'site'").fetchone()
    boss = logic.Viewer(c.get("/api/me", headers=A).json()["id"], "admin", True)
    assert school["official"] and logic.president_link(con, boss, school["id"])["token"]


def test_admin_row_role_is_one_transaction(env, monkeypatch):
    """A team row's action (userId) checks the membership and changes the role under one write lock: a removal from
    another connection can't land between the two and be undone by the role's upsert."""
    import dataclasses
    import sqlite3
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({20}))))
    who = lambda uid, first, username: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": first, "username": username}, BOT)}
    A = who(20, "Owner", "owner")
    c.get("/api/me", headers=A)
    mid = c.get("/api/me", headers=who(22, "Next", "next_one")).json()["id"]
    club = c.post("/api/admin/orgs", headers=A, json={"name": "Chess Club", "short": "ch", "emoji": "trophy_3d"}).json()
    put = lambda body: c.put(f"/api/admin/orgs/{club['id']}/role", headers=A, json=body)
    assert put({"who": "22", "role": "vice"}).status_code == 200
    other = db.connect(cfg.db_path)
    other.execute("PRAGMA busy_timeout = 0")
    seen = []
    real = logic.oversight.set_role

    def racing(con, *a, **k):  # the moment between the membership check and the change: another connection tries to remove
        seen.append(con.in_transaction)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            other.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (club["id"], mid))
        return real(con, *a, **k)
    monkeypatch.setattr(logic.oversight, "set_role", racing)
    assert put({"userId": mid, "role": "head"}).json()["team"][0]["role"] == "head" and seen == [True]
    # once it is done the removal goes through, and the row's next action finds nobody to act on
    other.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (club["id"], mid))
    assert put({"userId": mid, "role": "head"}).json()["message"] == "who" and len(seen) == 1
    assert c.get("/api/admin/orgs", headers=A).json()[0]["members"] == 0


def test_members_csv(env):
    """The roster file (Nov 5): the club's Vice+ only; only what the team sees (no student ID, email, phone);
    highest role first; every export in the audit log."""
    import codecs
    c, cfg = env
    pres, ali = login(c, 20, "pres"), login(c, 21, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0), (1, ?, 'member', 0)", (pres["id"], ali["id"]))
    con.execute("UPDATE students SET email = 'a@kbtu.kz', phone = '+77001234567' WHERE user_id = ?", (ali["id"],))
    assert c.post("/api/orgs/1/members/export", headers=tma(21, "Ali")).status_code == 403   # a plain member
    o, people = logic.members_export(con, logic.Viewer(pres["id"], "user", True), 1)
    name, data, caption = texts.members_csv("en", o["name"], people)
    assert name == "members.csv" and data.startswith(codecs.BOM_UTF8) and caption.startswith("Club members: IT Club")
    head, top, row = (r.split(";") for r in data.decode("utf-8-sig").splitlines())
    role = head.index("Role")
    assert "Middle name" not in head and "Department" not in head and "Position" not in head  # none, or empty: no column
    assert top[role] == "President" and row[role] == "Member" and row[head.index("First name (Latin)")] == "Ali*" and "generated automatically" in caption
    assert texts.latin("\u0414\u0430\u0443\u043b\u0435\u0442\u04b1\u043b\u044b") == "Dauletuly"
    assert "24Bali" not in data.decode("utf-8-sig") and "kbtu.kz" not in data.decode("utf-8-sig") and "7700" not in data.decode("utf-8-sig")
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'members_export'").fetchone()[0] == 1


def test_guard_join(env):
    """A chat that made our bot its guard: a student in, a banned person out, a stranger gets the app; the app's link
    is signed and only its own person can use it (Bot API 10.1 join request queries)."""
    from kbtu import bot
    c, cfg = env
    ann = login(c, 20, "ann")
    con = db.connect(cfg.db_path)
    assert logic.guard_join(con, -100, 20) == "queue"                      # a chat the app doesn't know: its admins decide
    con.execute("INSERT INTO chats (title, kind, url, tg_chat_id, status, created_at) VALUES ('G', 'group', 'https://t.me/g', -100, 'org', 0)")
    assert logic.guard_join(con, -100, 20) == "approve"
    assert logic.guard_join(con, -100, 999) == "app"                       # never signed in
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ann["id"],))
    assert logic.guard_join(con, -100, 20) == "decline"
    real, logic.seats.chat_join = logic.seats.chat_join, lambda *a: True  # an event's chat with a ticket: a ban still wins
    try:
        assert logic.guard_join(con, -100, 20) == "decline"
    finally:
        logic.seats.chat_join = real
    con.execute("UPDATE users SET banned_at = NULL WHERE id = ?", (ann["id"],))
    calls = []  # a plain join request (no guard query) in that linked chat: a student approved, a stranger left alone

    class Http:
        async def post(self, url, json):
            calls.append((url.rsplit("/", 1)[1], json["user_id"]))
    asyncio.run(bot._join(cfg, Http(), con, {"chat": {"id": -100}, "from": {"id": 20}}))
    asyncio.run(bot._join(cfg, Http(), con, {"chat": {"id": -100}, "from": {"id": 999}}))
    asyncio.run(bot._join(cfg, Http(), con, {"chat": {"id": -200}, "from": {"id": 20}}))   # a chat the app doesn't know
    assert calls == [("approveChatJoinRequest", 20)]
    key = bot.guard_key(cfg)
    t = logic.guard_token(key, -100, 20, "q:1")
    assert logic.guard_read(key, t) == (-100, 20, "q:1")
    assert c.post("/api/guard", headers=tma(20, "Ann"), json={"t": t[:-1] + ("1" if t[-1] == "0" else "0")}).status_code == 403   # forged
    login(c, 21, "bob")
    assert c.post("/api/guard", headers=tma(21, "Bob"), json={"t": t}).status_code == 403             # someone else's
    con.close()


def test_team_rank_rule(env):
    """The club's own team (SPEC §2): everyone in it sees the roster; Vice+ manage only people below them and give only
    roles below their own; the President hands the club over and becomes Vice; anyone but the President can leave."""
    c, cfg = env
    ids = {n: login(c, i, n)["id"] for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "memb"), (24, "out"))}
    H = {n: tma(i, n.title()) for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "memb"), (24, "out"))}
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(ids["pres"], "president"), (ids["vice"], "vice"), (ids["head"], "head"), (ids["memb"], "member")])
    roles = lambda: {m["fullName"].split()[-1].lower(): m["role"] for m in c.get("/api/orgs/1/members", headers=H["pres"]).json()}
    patch = lambda who, uid, role: c.patch(f"/api/orgs/1/members/{uid}", headers=H[who], json={"role": role})

    assert c.get("/api/orgs/1/members", headers=H["out"]).status_code == 403             # not in the club
    assert [m["role"] for m in c.get("/api/orgs/1/members", headers=H["memb"]).json()] == ["president", "vice", "head", "member"]
    assert patch("head", ids["memb"], "head").status_code == 403                          # a Head manages nobody
    assert patch("vice", ids["head"], "vice").status_code == 403                          # only roles below your own
    assert patch("vice", ids["pres"], "member").status_code == 403                        # only people below you
    assert patch("vice", ids["memb"], "head").status_code == 200 and roles()["memb"] == "head"
    assert patch("pres", ids["vice"], "member").status_code == 200 and roles()["vice"] == "member"
    assert c.delete(f"/api/orgs/1/members/{ids['pres']}", headers=H["pres"]).json()["message"] == "president"   # hand it over first
    assert c.delete(f"/api/orgs/1/members/{ids['vice']}", headers=H["vice"]).status_code == 204                 # leaving by yourself
    assert c.post("/api/orgs/1/transfer", headers=H["head"], json={"userId": ids["memb"]}).status_code == 403
    assert c.post("/api/orgs/1/transfer", headers=H["pres"], json={"userId": ids["out"]}).status_code == 404    # not in the club
    team = c.post("/api/orgs/1/transfer", headers=H["pres"], json={"userId": ids["head"]}).json()
    assert {m["fullName"].split()[-1].lower(): m["role"] for m in team} == {"head": "president", "pres": "vice", "memb": "head"}
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'presidency_transfer'").fetchone()[0] == 1


def test_invite_link(env):
    """A club's invite link (SPEC §4.5): Vice+ get a fresh one each time; a student who opens it is a Member at once (a
    pending application is settled); one person, once, within 48 hours; a member opening it doesn't use it up."""
    c, cfg = env
    pres, ali, zhan = login(c, 20, "pres"), login(c, 21, "ali"), login(c, 22, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    P, A, Z = tma(20, "Pres"), tma(21, "Ali"), tma(22, "Zhan")
    assert c.post("/api/orgs/1/invites", headers=A).status_code == 403                      # Vice+ only
    token = c.post("/api/orgs/1/invites", headers=P).json()["token"]
    assert re.fullmatch(r"[0-9a-f]{24}", token) and c.post("/api/orgs/1/invites", headers=P).json()["token"] != token   # fresh each time
    c.post("/api/orgs/1/join-requests", headers=A)                                           # applied earlier
    assert c.post(f"/api/invites/{token}", headers=tma(23, "Guest")).status_code == 401
    assert c.post(f"/api/invites/{token}", headers=P).status_code == 200                    # already in: not used up
    assert c.post(f"/api/invites/{token}", headers=A).json()["id"] == 1
    assert [(m["org"]["id"], m["role"]) for m in c.get("/api/me", headers=A).json()["memberships"]] == [(1, "member")]
    assert c.get("/api/orgs/1/join-requests", headers=P).json() == []                        # the application is settled
    assert c.post(f"/api/invites/{token}", headers=Z).status_code == 404                     # once
    late = c.post("/api/orgs/1/invites", headers=P).json()["token"]
    con.execute("UPDATE org_invites SET expires_at = 1 WHERE token = ?", (late,))
    assert c.post(f"/api/invites/{late}", headers=Z).status_code == 404                      # 48 hours


def test_showcase(env):
    """The showcase (SPEC §4.11): up to 6 keys — achievement codes and badges as b<event id> — kept in the order picked;
    junk is dropped; the card's shelf shows only what the person actually has."""
    c, cfg = env
    ali = login(c, 41, "ali")
    A = tma(41, "Ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, badge_name, created_at, updated_at)
        VALUES (9, 1, 'published', 'Hack', '305', 1700000000, 'laptop_3d', '#3B6BFF', 'Hacker', 0, 0)""")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, checked_in_at, created_at, updated_at) VALUES (9, ?, 'going', 'ABC234', 1700000100, 0, 0)", (ali["id"],))
    con.execute("INSERT INTO achievement_grants (user_id, code, created_at) VALUES (?, 'bugs', 0)", (ali["id"],))
    me = c.patch("/api/me", headers=A, json={"showcase": ["b9", "<script>", "bugs", "regular", "b9", 5, "nope"]}).json()
    assert me["showcase"] == ["b9", "bugs", "regular"]                       # known keys, deduped, in order
    card = c.get(f"/api/users/{ali['id']}", headers=A).json()
    assert card["shelf"] == ["b9", "bugs"]                                  # "regular" isn't earned yet
    assert len(c.patch("/api/me", headers=A, json={"showcase": ["bugs"] * 3 + [f"b{i}" for i in range(10)]}).json()["showcase"]) == 6


def test_posts(env):
    """News (SPEC §4.10): Head+ write their club's posts; only a broadcast org writes to every club member, and the bot
    tells them; the unread dot counts broadcasts until they're read; a club takes its post down; a photo must be one's own."""
    c, cfg = env
    head, mem, dmp = login(c, 51, "head"), login(c, 52, "mem"), login(c, 53, "dmp")
    H, M, D = tma(51, "Head"), tma(52, "Mem"), tma(53, "Dmp")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")  # posts: official (clubs.stories_open)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_broadcast, created_at) VALUES (2, 'dmp', 'office', 'DMP', 'DM', 'sparkles_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'head', 0), (1, ?, 'member', 0), (2, ?, 'head', 0)", (head["id"], mem["id"], dmp["id"]))
    post = {"title": "Hackathon teams", "body": "Sign up by Friday", "tag": "recruiting", "pinned": True}
    assert c.post("/api/orgs/1/posts", headers=M, json=post).status_code == 403                  # Head+ only
    assert c.post("/api/orgs/1/posts", headers=H, json={**post, "audience": "clubs"}).status_code == 400   # not a broadcast org
    assert c.post("/api/orgs/1/posts", headers=H, json={**post, "tag": "<b>"}).status_code == 400
    assert c.post("/api/orgs/1/posts", headers=H, json={**post, "photoId": 999}).status_code == 400
    r = c.post("/api/orgs/1/posts", headers=H, json={**post, "title": "https://t.me/+fWvpKlkKId9iMzgy"})
    assert r.status_code == 400 and r.json()["message"] == "link_title"                          # a bare link isn't a title
    p = c.post("/api/orgs/1/posts", headers=H, json=post).json()
    assert p["pinned"] and p["canDelete"] and p["photo"] is None
    assert [x["id"] for x in c.get("/api/posts?scope=subs", headers=M).json()] == [p["id"]]       # a member sees the club's post
    b = c.post("/api/orgs/2/posts", headers=D, json={"title": "No more club reports", "audience": "clubs"}).json()
    assert [r[0] for r in con.execute("SELECT kind FROM bot_outbox WHERE user_id = ?", (mem["id"],))] == ["broadcast"]
    assert c.get("/api/me", headers=M).json()["counters"]["unreadBroadcasts"] == 1
    assert c.get("/api/me", headers=D).json()["counters"]["unreadBroadcasts"] == 0               # the author has read it
    assert c.post("/api/posts/read", headers=M, json={"ids": [b["id"], "x"]}).status_code == 204
    assert c.get("/api/me", headers=M).json()["counters"]["unreadBroadcasts"] == 0
    # edit and pin (the club's Head+): text changes read "edited", a pin alone doesn't; one pinned post per club
    assert c.patch(f"/api/posts/{p['id']}", headers=M, json={"title": "Mine now"}).status_code == 403
    for bad in ({"title": "x"}, {"tag": "<b>"}, {"photoId": 999}, {"pinned": "yes"}, {}):
        assert c.patch(f"/api/posts/{p['id']}", headers=H, json=bad).status_code == 400, bad
    e = c.patch(f"/api/posts/{p['id']}", headers=H, json={"title": "Hackathon: teams of 4", "tag": None, "photoId": None}).json()
    assert (e["title"], e["tag"], e["body"], e["pinned"], e["canEdit"]) == ("Hackathon: teams of 4", None, "Sign up by Friday", True, True) and e["editedAt"]
    q = c.post("/api/orgs/1/posts", headers=H, json={"title": "Second"}).json()
    assert c.patch(f"/api/posts/{q['id']}", headers=H, json={"pinned": True}).json()["editedAt"] is None
    assert [(x["title"], x["pinned"]) for x in c.get("/api/posts?scope=subs", headers=M).json()] == [("Second", True), ("Hackathon: teams of 4", False)]
    assert c.get("/api/posts?scope=subs", headers=M).json()[0]["canEdit"] is False
    assert c.delete(f"/api/posts/{p['id']}", headers=M).status_code == 403
    assert c.delete(f"/api/posts/{p['id']}", headers=H).status_code == 204
    assert [r[0] for r in con.execute("SELECT target FROM audit_log WHERE action = 'post_hide'")] == [f"post:{p['id']}"]
    assert c.patch(f"/api/posts/{p['id']}", headers=H, json={"title": "Back?"}).status_code == 404
    assert [x["title"] for x in c.get("/api/posts?scope=subs", headers=M).json()] == ["Second"]


def test_invite_cards(env, monkeypatch):
    """Invites go out as our bot's card: a line of text and a button — the link only behind the button,
    never in the text; a club's card is for its Vice+ only."""
    import json
    import httpx
    c, cfg = env
    ali, mem = login(c, 61, "ali"), login(c, 62, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0), (1, ?, 'member', 0)", (ali["id"], mem["id"]))
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}})
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(telegram)))
    A = tma(61, "Ali")
    assert c.post("/api/share", headers=A, json={"kind": "rf"}).json() == {"id": "prep1"}
    card = sent[-1]["result"]
    url = card["reply_markup"]["inline_keyboard"][0][0]["url"]
    code = c.get("/api/me", headers=A).json()["referrals"]["code"]
    assert card["type"] == "article" and url.endswith(f"startapp=r_{code}")
    assert card["reply_markup"]["inline_keyboard"][0][0]["text"] == "\U0001f91d \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0432 \u0434\u0440\u0443\u0437\u044c\u044f"
    assert "http" not in card["input_message_content"]["message_text"] and "Ali T" in card["input_message_content"]["message_text"]
    assert c.post("/api/share", headers=A, json={"kind": "join", "id": 1}).status_code == 200
    assert "startapp=join_1_" in sent[-1]["result"]["reply_markup"]["inline_keyboard"][0][0]["url"]
    assert c.post("/api/share", headers=tma(62, "Mem"), json={"kind": "join", "id": 1}).status_code == 403
    assert c.post("/api/share", headers=A, json={"kind": "nope"}).status_code == 400
    assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "regular"}).status_code == 400    # not earned
    con.execute("INSERT INTO achievement_grants (user_id, code, created_at) VALUES (?, 'bugs', 0)", (ali["id"],))
    assert c.post("/api/share", headers=A, json={"kind": "aw", "code": "bugs"}).status_code == 200
    card = sent[-1]["result"]
    assert card["reply_markup"]["inline_keyboard"][0][0]["url"].endswith("startapp=aw_bugs") and "· I" in card["input_message_content"]["message_text"]
    # Admin → Badges, a link for everyone: the owner's alone; many open it, each gets the badge once
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (ali["id"],))
    assert c.post("/api/share", headers=A, json={"kind": "gl", "code": "creator_laugh"}).status_code == 403  # the creator's own: not an admin's
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ali["id"],))
    assert c.post("/api/share", headers=A, json={"kind": "gl", "code": "init26p", "uses": None, "days": 14}).status_code == 200
    token = sent[-1]["result"]["reply_markup"]["inline_keyboard"][0][0]["url"].split("gl_")[1]
    assert "\u0434\u043e" in sent[-1]["result"]["input_message_content"]["message_text"].lower()                   # "until" its day
    login(c, 63, "zed")
    assert c.post(f"/api/grant-links/{token}", headers=tma(62)).json() == c.post(f"/api/grant-links/{token}", headers=tma(63)).json() == {"code": "init26p"}
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE code = 'init26p'").fetchone()[0] == 2


def test_member_link(env):
    """"My link" (a member's KPI): who signs up by a club member's link (ev_<id>_<link code>, never the badge's secret)
    is that member's; the first link wins, never myself, never a stranger's code; the organizers see who brought whom,
    the Team page the ones who came, not counting those the member checked in themself."""
    c, cfg = env
    pres, ali, zhan, dana = login(c, 90, "pres"), login(c, 91, "ali"), login(c, 92, "zhan"), login(c, 93, "dana")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (int(time.time()) + 86400, pres["id"]))
    code = {u["id"]: logic._qr_code(con, u["id"], "link_code") for u in (pres, ali, dana)}
    assert logic._qr_code(con, ali["id"]) != code[ali["id"]]                                            # the badge keeps its own secret
    P, A, Z, D = tma(90, "Pres"), tma(91, "Ali"), tma(92, "Zhan"), tma(93, "Dana")
    by = lambda u: con.execute("SELECT invited_by FROM registrations WHERE user_id = ?", (u["id"],)).fetchone()[0]  # noqa: E731
    c.post("/api/events/1/registration", headers=A, json={"ref": code[ali["id"]]})
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (ali["id"],))  # a guest's seat from before he joined
    eve = login(c, 94, "eve")
    c.post("/api/events/1/registration", headers=tma(94, "Eve"), json={"ref": logic._qr_code(con, ali["id"])})
    assert by(eve) is None                                                                              # a badge's secret isn't a link
    c.delete("/api/events/1/registration", headers=tma(94, "Eve"))
    c.post("/api/events/1/registration", headers=D, json={"ref": code[dana["id"]]})
    assert by(ali) is None and by(dana) is None                                                         # myself; not in the club
    c.post("/api/events/1/registration", headers=Z, json={"ref": code[ali["id"]]})
    c.delete("/api/events/1/registration", headers=Z)
    c.post("/api/events/1/registration", headers=Z, json={"ref": code[pres["id"]]})
    assert by(zhan) == ali["id"]                                                                        # the first link wins
    seen = {a["person"]["id"]: a["by"] and a["by"]["id"] for a in c.get("/api/events/1/attendees", headers=P).json()}
    assert seen == {ali["id"]: None, dana["id"]: None, zhan["id"]: ali["id"]}                         # Eve cancelled: not listed
    con.execute("UPDATE registrations SET checked_in_at = ?, checked_in_by = ? WHERE user_id = ?", (int(time.time()), ali["id"], zhan["id"]))
    team = {m["person"]["id"]: m.get("brought") for m in c.get("/api/orgs/1/members", headers=P).json()}
    assert team == {pres["id"]: 0, ali["id"]: 0}                                                        # Ali checked his own friend in
    assert not next(a for a in c.get("/api/events/1/attendees", headers=P).json() if a["person"]["id"] == zhan["id"])["byCame"]
    con.execute("UPDATE registrations SET checked_in_by = ? WHERE user_id = ?", (pres["id"], zhan["id"]))
    team = {m["person"]["id"]: m.get("brought") for m in c.get("/api/orgs/1/members", headers=P).json()}
    assert team == {pres["id"]: 0, ali["id"]: 1}
    assert "brought" not in c.get("/api/orgs/1/members", headers=A).json()[0]                           # Head+ only


def test_registry(env, monkeypatch):
    """DMP's registry (§4.13): DMP Head+ only; every club with its numbers and President; rosters with full names and
    IDs, contacts only of Presidents and Vices; search finds club members only; the CSV goes to their chat."""
    import httpx
    c, cfg = env
    dmp, pres, ali, zhan = login(c, 80, "dmp"), login(c, 81, "pres"), login(c, 82, "ali"), login(c, 83, "zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", [(9, dmp["id"], "head"), (1, pres["id"], "president"), (1, ali["id"], "member")])
    con.execute("UPDATE users SET tg_username = 'pres_tg' WHERE id = ?", (pres["id"],))
    con.execute("UPDATE users SET tg_username = 'ali_tg' WHERE id = ?", (ali["id"],))
    D, A = tma(80, "Dmp"), tma(82, "Ali")
    assert c.get("/api/registry/orgs", headers=A).status_code == 403
    clubs = c.get("/api/registry/orgs", headers=D).json()
    it = next(x for x in clubs if x["org"]["id"] == 1)
    assert it["members"] == 2 and it["president"]["fullName"] == "Testov Pres" and it["president"]["username"] == "pres_tg"
    assert all(x["org"]["id"] != 9 for x in clubs)                                                       # offices aren't clubs
    assert c.get("/api/registry/orgs", headers=D, params={"back": 3}).status_code == 200 and c.get("/api/registry/orgs", headers=D, params={"back": 13}).status_code == 400
    roster = c.get("/api/registry/orgs/1/members", headers=D).json()
    assert [(x["role"], x["studentId"]) for x in roster] == [("president", "24Bpres"), ("member", "24Bali")]
    assert roster[1]["username"] is None and roster[1]["quiet"] is True                                # a member: no contacts
    assert [x["person"]["id"] for x in c.get("/api/registry/search", headers=D, params={"q": "24Bal"}).json()] == [ali["id"]]
    assert c.get("/api/registry/search", headers=D, params={"q": "Zhan"}).json() == []                 # in no club
    looks = [(r[0], r[1]) for r in con.execute("SELECT actor_id, action FROM audit_log WHERE action LIKE 'registry_%' ORDER BY id")]
    assert looks == [(dmp["id"], "registry_roster"), (dmp["id"], "registry_search"), (dmp["id"], "registry_search")]  # §9
    sent = []
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(
        lambda r: (sent.append(r.content), httpx.Response(200, json={"ok": True}))[1])))
    assert c.post("/api/registry/export", headers=D).status_code == 204
    assert b"Testov" in sent[0] and b"pres_tg" in sent[0] and b"ali_tg" not in sent[0]
    assert [r[0] for r in con.execute("SELECT actor_id FROM audit_log WHERE action = 'registry_export'")] == [dmp["id"]]  # §2
    # DMP gives the ✓ (and can take it back): the President hears it once; not for offices; never for a plain member
    assert c.post("/api/registry/orgs/1/official", headers=A, json={"on": True}).status_code == 403
    assert c.post("/api/registry/orgs/9/official", headers=D, json={"on": True}).status_code == 404
    assert c.post("/api/registry/orgs/1/official", headers=D, json={"on": "yes"}).status_code == 400
    assert c.post("/api/registry/orgs/1/official", headers=D, json={"on": True}).json()["official"] is True
    c.post("/api/registry/orgs/1/official", headers=D, json={"on": False}); c.post("/api/registry/orgs/1/official", headers=D, json={"on": True})
    told = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'club_official'").fetchall()
    assert [t["user_id"] for t in told] == [pres["id"]] and bot._render(con, told[0])[2] == "cl_1"
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'official'").fetchone()[0] == 3
    # (after the export: a request refreshes the person's Telegram fields from initData)
    team = {x["person"]["id"]: x["quiet"] for x in c.get("/api/orgs/1/members", headers=tma(81, "Pres")).json()}
    assert team[ali["id"]] is True and not any(x["quiet"] for x in c.get("/api/orgs/1/members", headers=A).json())  # Vice+ only


def test_feature_post(env):
    """A post for everyone on top of List (§2): moderators and the admin, public posts only, one at a time, 0 days ends it."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); pres = login(c, 61, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, official) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0, 1)")
    for pid, aud in ((1, "public"), (2, "public"), (3, "clubs")):
        con.execute("INSERT INTO posts (id, org_id, author_id, audience, title, body, created_at) VALUES (?, 1, ?, ?, 'T', 'B', 0)", (pid, pres["id"], aud))
    B, P = tma(60, "Boss"), tma(61, "Pres")
    feat = lambda pid, days, h=B: c.post("/api/admin/feature", headers=h, json={"postId": pid, "days": days})
    assert feat(1, 3, P).status_code == 403 and feat(3, 3).status_code == 400 and feat(1, 30).status_code == 400
    assert feat(1, 3).json()["featured"] is True
    feat(2, 3)
    got = {p["id"]: p["featured"] for p in c.get("/api/posts", headers=B, params={"scope": "all"}).json()}
    assert got == {1: False, 2: True}                                                           # one at a time
    assert feat(2, 0).json()["featured"] is False
    login(c, 62, "ali")
    react = lambda pid: c.put(f"/api/posts/{pid}/reactions/fire", headers=tma(62)).status_code  # noqa: E731
    assert react(1) == 200 and react(3) == 404             # a members-only broadcast doesn't leak through its reactions
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'member', 0 FROM users WHERE tg_id = 62")
    assert react(3) == 200                                 # a club member reacts to it as before
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert react(1) == 404                                 # nor a hidden club's post


def test_club_applications(env, monkeypatch):
    """Starting a club (§4.6): one pending application per person, the admins hear about it; yes = the club exists with
    the applicant as President; no = a reason, and a new application only in 30 days."""
    import dataclasses
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali = login(c, 61, "ali"); zhan = login(c, 62, "zhan")
    B, A, Z = tma(60, "Boss"), tma(61, "Ali"), tma(62, "Zhan")
    # A4: a name, a description, up to 6 social links
    links = ["https://instagram.com/chess.kbtu", "https://tiktok.com/@chesskbtu"]
    good = {"name": "Chess Club", "short": "CH", "description": "We play chess every week.", "emoji": "trophy_3d", "cover": 2, "links": links}
    assert c.post("/api/club-applications", headers=A, json={**good, "links": ["javascript:alert(1)"]}).status_code == 400
    assert c.post("/api/club-applications", headers=A, json={**good, "links": ["https://tiktok.com/@x"] * 7}).status_code == 400
    assert c.post("/api/club-applications", headers=A, json={**good, "links": "https://tiktok.com/@x"}).status_code == 400
    assert c.post("/api/club-applications", headers=A, json={**good, "links": ["https://tiktok.com/@x"] * 2}).status_code == 400  # keyed in the app
    app = c.post("/api/club-applications", headers=A, json=good).json()
    assert app["links"] == links and app["why"] is None
    assert app["status"] == "pending" and c.post("/api/club-applications", headers=A, json=good).json()["message"] == "pending"
    con = db.connect(cfg.db_path)
    ping = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'club_application'").fetchall()
    assert len(ping) == 1 and bot._render(con, ping[0])[2] == "capps"                               # the admin hears
    assert c.get("/api/me", headers=B).json()["counters"]["inbox"] == 1
    assert c.get("/api/admin/inbox", headers=A).status_code == 403
    # all or nothing: a failure after the club is made leaves no club without its President, and the application waits
    real = logic.set_role
    monkeypatch.setattr(logic.oversight, "set_role", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        c.post(f"/api/admin/club-applications/{app['id']}", headers=B, json={"approve": True})
    monkeypatch.setattr(logic.oversight, "set_role", real)
    assert not con.execute("SELECT 1 FROM orgs WHERE name = 'Chess Club'").fetchone()
    assert c.get("/api/club-applications/mine", headers=A).json()["application"]["status"] == "pending"
    done = c.post(f"/api/admin/club-applications/{app['id']}", headers=B, json={"approve": True}).json()
    assert done["status"] == "approved" and done["applicant"]["fullName"] == "Testov Ali"
    me = c.get("/api/me", headers=A).json()
    assert [(m["org"]["name"], m["role"]) for m in me["memberships"]] == [("Chess", "president")]
    assert c.get(f"/api/orgs/{done['orgId']}", headers=A).json()["links"] == links           # the club got them all
    told = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'club_application_decided'").fetchone()
    assert bot._render(con, told)[2] == f"cl_{done['orgId']}"
    go = {**good, "name": "Go Club", "links": ["https://tiktok.com/@go"], "why": "Weekly games"}
    z = c.post("/api/club-applications", headers=Z, json=go).json()
    assert (z["links"], z["why"]) == (go["links"], go["why"])
    assert c.post(f"/api/admin/club-applications/{z['id']}", headers=B, json={"approve": False}).status_code == 400  # a reason
    assert c.post(f"/api/admin/club-applications/{z['id']}", headers=B, json={"approve": False, "reason": "There is a Go club already"}).json()["status"] == "rejected"
    assert c.get("/api/club-applications/mine", headers=Z).json()["application"]["reason"] == "There is a Go club already"
    assert c.post("/api/club-applications", headers=Z, json={**good, "name": "Go Club 2"}).status_code == 429  # 30 days


def test_president_link(env, monkeypatch):
    """A new club's President by link (§2): only the admin makes one, as our bot's card; the first student to open it
    leads the club (the old President steps down to Vice); once, within 7 days; a new link ends the unused old one."""
    import dataclasses
    import json
    import httpx
    c, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({60}))))
    login(c, 60, "boss"); ali, zhan, old = login(c, 61, "ali"), login(c, 62, "zhan"), login(c, 63, "old")
    B, A, Z = tma(60, "Boss"), tma(61, "Ali"), tma(62, "Zhan")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'chess', 'club', 'Chess Club', 'CH', 'trophy_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (old["id"],))
    sent = []
    real = httpx.AsyncClient
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(
        lambda r: (sent.append(json.loads(r.content)), httpx.Response(200, json={"ok": True, "result": {"id": "prep"}}))[1])))
    assert c.post("/api/share", headers=A, json={"kind": "pres", "id": 1}).status_code == 403             # the admin only
    start = lambda: re.search(r"startapp=pres_1_([0-9a-f]{24})", sent[-1]["result"]["reply_markup"]["inline_keyboard"][0][0]["url"]).group(1)  # noqa: E731
    assert c.post("/api/share", headers=B, json={"kind": "pres", "id": 1}).status_code == 200
    first = start()
    assert "http" not in sent[-1]["result"]["input_message_content"]["message_text"]
    c.post("/api/share", headers=B, json={"kind": "pres", "id": 1})
    token = start()
    assert c.post(f"/api/invites/{first}", headers=A).status_code == 404                                  # replaced
    assert c.post(f"/api/invites/{token}", headers=A).json()["myRole"] == "president"
    roles = dict(con.execute("SELECT user_id, role FROM org_members WHERE org_id = 1").fetchall())
    assert roles == {ali["id"]: "president", old["id"]: "vice"}
    assert c.post(f"/api/invites/{token}", headers=Z).status_code == 404                                  # once
    c.post("/api/share", headers=B, json={"kind": "pres", "id": 1})
    con.execute("UPDATE org_invites SET expires_at = 1 WHERE token = ?", (start(),))
    assert c.post(f"/api/invites/{start()}", headers=Z).status_code == 404                                # 7 days


def test_club_profile(env):
    """The club's own profile (Vice+, §2): name, two letters, emoji, cover, about, links, logo — only what is sent changes;
    a member can't; a taken name, a bad link or a stray value are refused and nothing changes."""
    c, cfg = env
    vice, mem = login(c, 20, "vice"), login(c, 21, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0), "
                "(2, 'go', 'club', 'Go', 'GO', 'trophy_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0), (1, ?, 'member', 0)", (vice["id"], mem["id"]))
    V, M = tma(20, "Vice"), tma(21, "Mem")
    patch = {"name": "IT KBTU", "short": "it", "emoji": "rocket_3d", "cover": 4, "description": "We build things.",
             "links": ["https://instagram.com/itclub", "https://tiktok.com/@itclub"]}
    assert c.patch("/api/orgs/1", headers=M, json=patch).status_code == 403
    o = c.patch("/api/orgs/1", headers=V, json=patch).json()
    assert (o["name"], o["short"], o["emoji"], o["cover"], o["description"], o["links"], o["recruiting"]) == \
        ("IT", "IT", "rocket_3d", 4, "We build things.", patch["links"], True)  # "KBTU" goes
    assert c.patch("/api/orgs/1", headers=V, json={"recruiting": False}).json()["name"] == "IT"   # one field at a time
    assert c.patch("/api/orgs/1", headers=V, json={"name": "go"}).json()["message"] == "taken"
    for bad in ({"links": ["javascript:alert(1)"]}, {"links": ["https://a.kz"] * 7}, {"cover": 9}, {"short": "ABC"}, {"emoji": "../x"},
                {"name": "X"}, {"name": "IT Club"}, {"name": "\u041a\u043b\u0443\u0431 \u0434\u0435\u0431\u0430\u0442\u043e\u0432"}, {"name": "IT \U0001f680"},
                {"description": "x" * 601}, {}, {"description": "ok", "cover": True}):
        assert c.patch("/api/orgs/1", headers=V, json=bad).status_code == 400, bad
    assert c.get("/api/orgs/1", headers=M).json()["description"] == "We build things."                    # nothing half-saved
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'org_edit'").fetchone()[0] == 1

    # the logo: the editor's own upload goes on and shows wherever the club does; a stray id doesn't; null takes it off
    import io
    from PIL import Image
    raw = io.BytesIO()
    Image.new("RGB", (600, 600), (40, 90, 200)).save(raw, "PNG")
    up = c.post("/api/photos", headers=V, content=raw.getvalue()).json()
    assert c.patch("/api/orgs/1", headers=V, json={"logoId": up["id"]}).json()["logo"] == up["thumb"]
    assert c.get("/api/me", headers=M).json()["memberships"][0]["org"]["logo"] == up["thumb"]
    for bad in ({"logoId": up["id"] + 1}, {"logoId": str(up["id"])}, {"logoId": True}):
        assert c.patch("/api/orgs/1", headers=V, json=bad).status_code == 400, bad
    assert c.patch("/api/orgs/1", headers=V, json={"logoId": None}).json()["logo"] is None
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'org_edit'").fetchone()[0] == 3


def test_meetings(env):
    """Studio part 2 (§2b): a meeting the whole club (or a tag) is expected at. Everyone expected hears; "can't" needs a
    reason; Head+ see the answers and who came; the door lists everyone expected and
    lets in someone who came anyway; others don't see it."""
    c, cfg = env
    pres, head, mem, mem2, out = login(c, 80, "pres"), login(c, 81, "head"), login(c, 82, "mem"), login(c, 83, "mem2"), login(c, 84, "out")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at, probation) VALUES (1, ?, ?, 0, ?)",
                    [(pres["id"], "president", 0), (head["id"], "head", 0), (mem["id"], "member", 1), (mem2["id"], "member", 1)])
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (5, 1, 'SMM', '#FF4FA3', 0)")
    con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (5, ?)", (mem2["id"],))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'art', 'club', 'Art', 'A', 'art_3d', 0)")
    con.execute("INSERT INTO org_tags (id, org_id, name, color, created_at) VALUES (6, 2, 'Other', '#FF4FA3', 0)")  # another club's tag
    H = tma(81, "Head")
    start = int(time.time()) + 3600
    body = {"title": "Weekly sync", "place": "305", "startsAt": start, "endsAt": start + 3600, "emoji": "laptop_3d", "color": "#3B6BFF",
            "seats": None, "visibility": "members", "meeting": True}
    for bad in ({"visibility": "public"}, {"seats": 10}, {"meetingTag": 6}, {"price": 1000, "payToName": "IT Club", "payPhone": "+77010000000"}):
        assert c.post("/api/orgs/1/events", headers=H, json={**body, **bad}).status_code in (400, 403), bad
    ev = c.post("/api/orgs/1/events", headers=H, json=body).json()
    assert ev["meeting"] is True and ev["meetingTag"] is None
    c.post(f"/api/events/{ev['id']}/publish", headers=H)
    invited = {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'meeting_invite'")}
    assert invited == {pres["id"], mem["id"], mem2["id"]}                        # everyone but the one who published
    assert c.get(f"/api/events/{ev['id']}", headers=tma(84)).status_code == 404  # not their club
    M, M2 = tma(82, "Mem"), tma(83, "Mem2")
    assert c.post(f"/api/events/{ev['id']}/decline", headers=M, json={}).json()["message"] == "note"   # why, please
    assert c.post(f"/api/events/{ev['id']}/decline", headers=M, json={"note": "Exam  at 6"}).json()["my"]["note"] == "Exam at 6"
    assert c.post(f"/api/events/{ev['id']}/registration", headers=M2, json={}).json()["my"]["status"] == "going"
    assert c.get(f"/api/events/{ev['id']}/meeting", headers=M2).status_code == 403                  # Head+ only
    ans = {a["person"]["id"]: a for a in c.get(f"/api/events/{ev['id']}/meeting", headers=H).json()}
    assert (ans[mem["id"]]["answer"], ans[mem["id"]]["note"]) == ("no", "Exam at 6") and ans[mem2["id"]]["answer"] == "yes"
    assert ans[pres["id"]]["answer"] == "none" and "probation" not in ans[pres["id"]]
    assert ans[mem["id"]]["probation"] and not ans[head["id"]]["probation"]
    door = {d["person"]["id"] for d in c.get(f"/api/events/{ev['id']}/door", headers=H).json()}
    assert door == {pres["id"], head["id"], mem["id"], mem2["id"]}                                    # everyone expected
    # it happens: mem said no but came; mem2 said yes and didn't; the door lets mem in by name
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 600, int(time.time()) + 600, ev["id"]))
    assert c.post(f"/api/events/{ev['id']}/checkin", headers=H, json={"userId": mem["id"]}).json()["result"] == "ok"
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?", (int(time.time()) - 7200, int(time.time()) - 3600, ev["id"]))
    ans = {a["person"]["id"]: a for a in c.get(f"/api/events/{ev['id']}/meeting", headers=H).json()}
    assert ans[mem["id"]]["came"] and not ans[mem2["id"]]["came"]
    assert ans[mem["id"]]["note"] == "Exam at 6"                     # said no (why), came: the reason stays (codex ideas2 3)
    # a tag's meeting expects only the tag's people
    tagged = c.post("/api/orgs/1/events", headers=H, json={"seats": None, **body, "meetingTag": 5, "startsAt": start + 86400, "endsAt": start + 90000}).json()
    c.post(f"/api/events/{tagged['id']}/publish", headers=H)
    assert {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'meeting_invite' AND ref = ?", (f"mi:{tagged['id']}",))} == {mem2["id"]}
    assert [a["person"]["id"] for a in c.get(f"/api/events/{tagged['id']}/meeting", headers=H).json()] == [mem2["id"]]


def test_leaders_meeting(env):
    """A leaders meeting (§4.10): only an oversight org makes one; it invites every club's leaders from the chosen role up
    (the bot at once); they answer yes or no; DMP sees the answers per club; nobody else sees the event."""
    c, cfg = env
    dmp, pres, vice, mem = login(c, 80, "dmp"), login(c, 81, "pres"), login(c, 82, "vice"), login(c, 83, "mem")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", [(9, dmp["id"], "head"), (1, pres["id"], "president"), (1, vice["id"], "vice"), (1, mem["id"], "member")])
    D, P, V, M = tma(80, "Dmp"), tma(81, "Pres"), tma(82, "Vice"), tma(83, "Mem")
    body = {"seats": None, "title": "Leaders meeting", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "trophy_3d", "color": "#3B6BFF",
            "visibility": "leaders", "leadersFrom": "vice"}
    assert c.post("/api/orgs/1/events", headers=P, json=body).status_code == 400              # not an oversight org
    e = c.post("/api/orgs/9/events", headers=D, json=body).json()
    c.post(f"/api/events/{e['id']}/publish", headers=D)
    asked = sorted(r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'leaders_invite'"))
    assert asked == sorted([pres["id"], vice["id"]])                                             # from Vice up
    assert [x["id"] for x in c.get("/api/events", headers=P).json()] == [e["id"]] and c.get("/api/events", headers=M).json() == []
    c.post(f"/api/events/{e['id']}/registration", headers=P)
    assert c.post(f"/api/events/{e['id']}/decline", headers=V).json()["my"]["status"] == "cancelled"
    answers = c.get(f"/api/events/{e['id']}/leaders", headers=D).json()
    assert [(a["org"]["id"], sorted(p["answer"] for p in a["people"])) for a in answers] == [(1, ["no", "yes"])]
    assert c.get(f"/api/events/{e['id']}/leaders", headers=P).status_code == 403


def test_departments(env):
    """Departments (PLAN item 47): tags marked department, a person in several or none, each given or taken alone. A
    Vice+ gives and takes any on anyone; a Head only their own (given by hand) on those below them, never themselves;
    plain tags leave the departments alone."""
    c, cfg = env
    for tg, name in ((20, "pres"), (21, "vic"), (22, "hed"), (23, "hed2"), (10, "ann"), (11, "bob")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    for tg, role in ((20, "president"), (21, "vice"), (22, "head"), (23, "head"), (10, "member"), (11, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, ?, 0 FROM users WHERE tg_id = ?", (role, tg))
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22, 23, 10, 11)}
    put = lambda by, tg, body: c.patch(f"/api/orgs/1/members/{uid[tg]}", headers=tma(by), json=body)  # noqa: E731
    depts = lambda tg: next(m for m in c.get("/api/orgs/1/members", headers=tma(20)).json() if m["person"]["id"] == uid[tg])["depts"]  # noqa: E731
    tags = c.post("/api/orgs/1/tags", headers=tma(21), json={"name": "SMM", "color": "#18A9DB", "department": True}).json()["tags"]
    smm = tags[0]["id"]
    assert tags[0]["department"] is True
    dev = c.post("/api/orgs/1/tags", headers=tma(21), json={"name": "Dev", "color": "#2FBF71", "department": True}).json()["tags"][1]["id"]
    star = c.post("/api/orgs/1/tags", headers=tma(21), json={"name": "Star", "color": "#FFB23D"}).json()["tags"][2]["id"]
    assert put(21, 22, {"addDept": smm}).status_code == 200 and put(21, 23, {"addDept": dev}).status_code == 200
    assert put(21, 10, {"addDept": star}).status_code == 400                    # a plain tag isn't a department
    assert put(21, 10, {"dept": smm}).status_code == 400                        # the one-department field is gone
    assert put(22, 10, {"addDept": smm}).status_code == 200 and depts(10) == [smm]  # a Head: into their own
    assert put(22, 10, {"addDept": dev}).status_code == 403                     # not into another's
    assert put(23, 10, {"dropDept": smm}).status_code == 403                    # not out of another's
    assert put(22, 22, {"dropDept": smm}).status_code == 403                    # not themselves
    assert put(22, 23, {"addDept": smm}).status_code == 403                     # not a peer
    assert put(23, 10, {"addDept": dev}).status_code == 200 and depts(10) == sorted([smm, dev])  # several at once
    assert put(21, 10, {"tags": [star]}).status_code == 200 and depts(10) == sorted([smm, dev])  # tags leave departments alone
    assert put(23, 10, {"dropDept": dev}).status_code == 200 and depts(10) == [smm]  # the other one stays
    meet = {"title": "SMM sync", "place": "305", "startsAt": int(time.time()) + 86400, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": None, "visibility": "members", "meeting": True}
    assert c.post("/api/orgs/1/events", headers=tma(22), json={**meet, "meetingTag": dev}).json().get("message") == "dept"  # PLAN 35
    assert c.post("/api/orgs/1/events", headers=tma(22), json=meet).json().get("message") == "dept"                # not the whole club
    assert c.post("/api/orgs/1/events", headers=tma(22), json={**meet, "meetingTag": smm}).status_code == 200
    assert c.post("/api/orgs/1/events", headers=tma(21), json=meet).status_code == 200                              # a Vice calls anyone
    assert c.get("/api/orgs/1/team", headers=tma(22)).json()["myDepts"] == [smm]
    # a department the chat sync gave a Head is theirs, but gives no powers over it
    con.execute("INSERT INTO member_tags (tag_id, user_id, sync) VALUES (?, ?, 1)", (dev, uid[22]))
    assert depts(22) == sorted([smm, dev]) and c.get("/api/orgs/1/team", headers=tma(22)).json()["myDepts"] == [smm]
    assert put(22, 11, {"addDept": dev}).status_code == 403
    assert c.post("/api/orgs/1/events", headers=tma(22), json={**meet, "meetingTag": dev}).json().get("message") == "dept"
    assert c.post("/api/orgs/1/invites", headers=tma(22), json={"dept": dev}).status_code == 403
    assert put(21, 22, {"addDept": dev}).status_code == 200 and c.get("/api/orgs/1/team", headers=tma(22)).json()["myDepts"] == sorted([smm, dev])  # by hand: now theirs
    assert put(21, 22, {"dropDept": dev}).status_code == 200
    assert put(22, 11, {"addDept": smm}).status_code == 200
    assert c.patch(f"/api/orgs/1/tags/{smm}", headers=tma(22), json={"name": "SMM", "color": "#18A9DB", "department": False}).status_code == 403  # Vice+ only
    assert c.post("/api/orgs/1/tags", headers=tma(22), json={"name": "Mine", "color": "#18A9DB", "department": True}).status_code == 403
    assert c.delete(f"/api/orgs/1/tags/{smm}", headers=tma(22)).status_code == 403                    # nor deletes one
    assert c.patch(f"/api/orgs/1/tags/{smm}", headers=tma(22), json={"name": "SMM team", "color": "#18A9DB", "department": True}).status_code == 200  # a rename is fine
    c.patch(f"/api/orgs/1/tags/{smm}", headers=tma(21), json={"name": "SMM", "color": "#18A9DB", "department": False})
    assert depts(11) == [] and smm in next(m for m in c.get("/api/orgs/1/members", headers=tma(20)).json() if m["person"]["id"] == uid[11])["tags"]
    login(c, 12, "cat"); login(c, 13, "dan")                                     # a link straight into a department
    assert c.post("/api/orgs/1/invites", headers=tma(21), json={"dept": star}).status_code == 400
    assert c.post("/api/orgs/1/invites", headers=tma(21), json={"dept": "x"}).status_code == 400
    tok = c.post("/api/orgs/1/invites", headers=tma(21), json={"dept": dev}).json()["token"]
    assert c.post(f"/api/invites/{tok}", headers=tma(12)).status_code == 200
    uid[12] = con.execute("SELECT id FROM users WHERE tg_id = 12").fetchone()[0]
    assert depts(12) == [dev]
    tok = c.post("/api/orgs/1/invites", headers=tma(21)).json()["token"]                # no department, as before
    assert c.post(f"/api/invites/{tok}", headers=tma(13)).status_code == 200
    uid[13] = con.execute("SELECT id FROM users WHERE tg_id = 13").fetchone()[0]
    assert depts(13) == []


def test_team_two(env):
    """Team 2.0 (§2b): the club's own roles are a name on a level (Vice+, strictly below their own); tags are groups
    (Head+); probation is a label (Head+ put it on, the person and Head+ see it, a Vice+ takes it off); a Head's removal is a request, a Vice+ removes at once; a ban keeps
    them out of applications and the link until lifted."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "vic"), (22, "hed"), (10, "ann"), (11, "bob"), (12, "cat")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    for tg, role in ((20, "president"), (21, "vice"), (22, "head"), (10, "member"), (11, "member"), (12, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, ?, 0 FROM users WHERE tg_id = ?", (role, tg))
    uid = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22, 10, 11, 12)}
    member = lambda viewer, tg: next(m for m in c.get("/api/orgs/1/members", headers=tma(viewer)).json() if m["person"]["id"] == uid[tg])  # noqa: E731
    outbox = lambda kind: [r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = ?", (kind,))]  # noqa: E731

    # roles: a name and colour on a level below the maker's own
    smm = {"name": "SMM lead", "color": "#FF4FA3", "rights": list(logic.LEVEL_RIGHTS["head"])}
    vice_rights = list(logic.LEVEL_RIGHTS["vice"])
    assert c.post("/api/orgs/1/roles", headers=tma(22), json=smm).status_code == 403                  # a Head makes none
    assert c.post("/api/orgs/1/roles", headers=tma(21), json={**smm, "rights": vice_rights}).status_code == 403
    for bad in ({"color": "pink"}, {"name": ""}, {"name": "x" * 25}, {"rights": ["president"]}):
        assert c.post("/api/orgs/1/roles", headers=tma(21), json={**smm, **bad}).status_code == 400
    rid = c.post("/api/orgs/1/roles", headers=tma(21), json=smm).json()["roles"][0]["id"]
    assert c.post("/api/orgs/1/roles", headers=tma(20), json={**smm, "name": "smm LEAD"}).json()["message"] == "taken"
    treasurer = c.post("/api/orgs/1/roles", headers=tma(20), json={"name": "Treasurer", "color": "#2FBF71", "rights": vice_rights}).json()["roles"][1]["id"]
    assert c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"roleId": treasurer}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"roleId": rid})
    ann = member(11, 10)
    assert (ann["role"], ann["title"], ann["titleColor"]) == ("head", "SMM lead", "#FF4FA3")
    assert c.get("/api/me", headers=tma(10)).json()["memberships"][0]["title"] == "SMM lead"
    assert c.get("/api/orgs/1", headers=tma(10)).json()["myTitle"] == "SMM lead"
    # its title in Kazakh and English: everywhere the title goes (typed once in English here; the AI's turn: test_role_titles)
    kk = "SMM \u0436\u0435\u0442\u0435\u043a\u0448\u0456\u0441\u0456"
    for bad in ({"tr": {"kk": "x" * 25}}, {"tr": "kk"}):
        assert c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(21), json={**smm, **bad}).status_code == 400
    role = next(r for r in c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(21), json={**smm, "tr": {"kk": f" {kk} ", "en": "ignored: the typed one"}}).json()["roles"] if r["id"] == rid)
    assert (role["name"], role["nameKk"], role["nameEn"], role["src"], role["hand"]) == ("SMM lead", kk, "SMM lead", "en", ["kk"])
    titles = lambda o, k="title": (o[k], o[k + "Kk"], o[k + "En"])  # noqa: E731
    want = ("SMM lead", kk, "SMM lead")
    assert titles(member(11, 10)) == titles(c.get("/api/me", headers=tma(10)).json()["memberships"][0]) == want
    assert titles(c.get("/api/orgs/1", headers=tma(10)).json(), "myTitle") == want
    assert titles(c.get(f"/api/users/{uid[10]}", headers=tma(11)).json()["clubs"][0]) == want
    assert titles(next(m for m in c.get("/api/orgs/1/people", headers=tma(11)).json() if m["person"]["id"] == uid[10])) == want
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(21), json=smm)                     # no `tr`: the correction stays
    assert titles(member(11, 10)) == want
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(21), json={**smm, "tr": {}})        # dropped: the AI's again
    assert titles(member(11, 10)) == ("SMM lead", None, "SMM lead")
    # the memo signs with them; a known word still wins
    assert texts.memo_pos("head", "SMM lead", kk, None) == {"kk": kk, "ru": "SMM lead", "en": "SMM lead"}
    assert texts.memo_pos("head", "Head of SMM", kk, "x") == texts.memo_pos("head", "Head of SMM")
    assert c.patch(f"/api/orgs/1/roles/{treasurer}", headers=tma(21), json={**smm, "name": "Cash"}).status_code == 403
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(20), json={**smm, "rights": ["door"]})          # its people move with it
    assert member(20, 10)["role"] == "member"
    c.delete(f"/api/orgs/1/roles/{rid}", headers=tma(21))
    assert (member(20, 10)["role"], member(20, 10)["title"]) == ("member", None)
    assert c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"role": "head"}).json()[2]["role"] == "head"  # the old way still works
    c.patch(f"/api/orgs/1/members/{uid[10]}", headers=tma(21), json={"role": "member"})

    # the toggles: a role is its rights; the highest ranks it; only rights I have, below my level
    made = c.post("/api/orgs/1/roles", headers=tma(21), json={"name": "SMM", "color": "#FF4FA3", "rights": ["posts", "posts"]}).json()["roles"]
    r_smm = next(r for r in made if r["name"] == "SMM")
    assert (r_smm["rights"], r_smm["level"]) == (["door", "posts"], "head")  # the door is everyone's
    assert c.post("/api/orgs/1/roles", headers=tma(21), json={"name": "Cashier", "color": "#2FBF71", "rights": ["money"]}).status_code == 403
    assert c.post("/api/orgs/1/roles", headers=tma(21), json={"name": "X", "color": "#2FBF71", "rights": ["nope"]}).status_code == 400
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(21), json={"roleId": r_smm["id"]})
    assert c.get("/api/me", headers=tma(11)).json()["memberships"][0]["rights"] == ["door", "posts"]
    assert c.get("/api/orgs/1", headers=tma(11)).json()["myRights"] == ["door", "posts"]
    post = {"title": "Hello", "body": "We meet on Friday", "audience": "public"}
    assert c.post("/api/orgs/1/posts", headers=tma(11), json=post).status_code == 200            # their toggle
    assert c.post("/api/orgs/1/tags", headers=tma(11), json={"name": "Nope", "color": "#18A9DB"}).status_code == 403  # not theirs
    assert c.get("/api/orgs/1/join-requests", headers=tma(11)).status_code == 403
    assert c.get("/api/me", headers=tma(22)).json()["memberships"][0]["rights"] == ["door", "events", "posts", "people", "casting"]  # a level: its rights
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(21), json={"role": "member"})
    c.delete(f"/api/orgs/1/roles/{r_smm['id']}", headers=tma(21))

    # tags: groups of people, Head+, on themselves or anyone below them
    assert c.post("/api/orgs/1/tags", headers=tma(10), json={"name": "SMM", "color": "#18A9DB"}).status_code == 403
    tag = c.post("/api/orgs/1/tags", headers=tma(22), json={"name": "SMM", "color": "#18A9DB"}).json()["tags"][0]["id"]
    assert c.patch(f"/api/orgs/1/members/{uid[22]}", headers=tma(22), json={"tags": [tag]}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(22), json={"tags": [tag]}).status_code == 403
    assert c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"tags": [tag + 99]}).status_code == 400
    # the Vice and the President tag each other and themselves; a Vice takes a role of their own level
    assert c.patch(f"/api/orgs/1/members/{uid[20]}", headers=tma(21), json={"tags": [tag]}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[20]}", headers=tma(20), json={"tags": []}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(21), json={"roleId": treasurer}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(21), json={"role": "head"}).status_code == 403
    assert c.patch(f"/api/orgs/1/members/{uid[20]}", headers=tma(21), json={"roleId": treasurer}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[21]}", headers=tma(20), json={"role": "vice"})
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"tags": [tag]})
    assert member(12, 11)["tags"] == [tag] and c.get("/api/orgs/1/team", headers=tma(12)).json()["tags"][0]["count"] == 2
    assert "removals" not in c.get("/api/orgs/1/team", headers=tma(22)).json()                         # Vice+ only

    # probation: a label Head+ put on, only the President or a Vice take off (passed: the bot congratulates)
    assert c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(10), json={"probation": True}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"probation": True})
    assert member(22, 11)["probation"] and member(11, 11)["probation"] and "probation" not in member(12, 11)  # theirs and the leaders' only
    assert "probation" not in member(22, 21) and "probation" in member(21, 22)                    # a Head can't see the Vice's (L10)
    assert texts._cell("\t=1+1") == "'\t=1+1" and texts._cell("\r@x")[0] == "'"                  # CSV: no formula behind a tab (L4)
    assert c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(22), json={"probation": False}).status_code == 403
    c.patch(f"/api/orgs/1/members/{uid[11]}", headers=tma(21), json={"probation": False})               # passed
    assert not member(22, 11)["probation"] and outbox("probation_passed") == [uid[11]]

    # removal: a Head asks, the President or a Vice decides; a ban keeps them out until lifted
    assert c.post(f"/api/orgs/1/members/{uid[12]}/remove", headers=tma(10), json={}).status_code == 403
    assert c.post(f"/api/orgs/1/members/{uid[12]}/remove", headers=tma(22), json={"ban": True, "note": "spam"}).json() == {"done": False}
    q = c.get("/api/orgs/1/team", headers=tma(20)).json()["removals"][0]
    assert (q["by"]["id"], q["ban"], q["note"]) == (uid[22], True, "spam")
    ask = con.execute("SELECT ref, user_id FROM bot_outbox WHERE kind = 'removal_ask' AND ref = ?", (f"rm:{q['id']}",)).fetchone()
    assert "and ban them" in bot._render(con, {"kind": "removal_ask", "ref": ask[0], "lang": "en", "user_id": ask[1]})[0]
    notice = {"kind": "removal_ask", "ref": ask[0], "lang": "en", "user_id": uid[21]}
    assert bot._render(con, notice)
    con.execute("UPDATE org_members SET role = 'member' WHERE org_id = 1 AND user_id = ?", (uid[21],))
    assert bot._render(con, notice) is None
    con.execute("UPDATE org_members SET role = 'vice' WHERE org_id = 1 AND user_id = ?", (uid[21],))
    assert c.post(f"/api/removals/{q['id']}", headers=tma(22), json={"approve": True}).status_code == 403
    c.post(f"/api/removals/{q['id']}", headers=tma(20), json={"approve": False})
    assert member(20, 12)["role"] == "member"                                                         # kept
    q = c.post(f"/api/orgs/1/members/{uid[12]}/remove", headers=tma(22), json={"ban": True}).json()
    rid2 = c.get("/api/orgs/1/team", headers=tma(21)).json()["removals"][0]["id"]
    assert c.post(f"/api/removals/{rid2}", headers=tma(21), json={"approve": True}).status_code == 204
    assert c.post(f"/api/removals/{rid2}", headers=tma(20), json={"approve": True}).status_code == 409  # answered already
    assert all(m["person"]["id"] != uid[12] for m in c.get("/api/orgs/1/members", headers=tma(20)).json())
    assert c.post("/api/orgs/1/join-requests", headers=tma(12)).json()["message"] == "banned"
    token = c.post("/api/orgs/1/invites", headers=tma(21)).json()["token"]
    assert c.post(f"/api/invites/{token}", headers=tma(12)).json()["message"] == "banned"
    assert [b["person"]["id"] for b in c.get("/api/orgs/1/team", headers=tma(21)).json()["bans"]] == [uid[12]]
    assert c.delete(f"/api/orgs/1/bans/{uid[12]}", headers=tma(22)).status_code == 403
    assert c.delete(f"/api/orgs/1/bans/{uid[12]}", headers=tma(21)).status_code == 204
    assert c.post(f"/api/invites/{token}", headers=tma(12)).status_code == 200                           # back by the link
    assert c.post(f"/api/orgs/1/members/{uid[11]}/remove", headers=tma(21), json={}).json() == {"done": True}  # a Vice at once


def test_important_post(env):
    """An "Important" post: Vice+ write it; the club's members (not the author) hear it from the bot, one
    such message a day per club at most; other labels message nobody."""
    from kbtu import bot
    c, cfg = env
    vice, head, mem = login(c, 61, "vice"), login(c, 62, "head"), login(c, 63, "mem")
    V, H = tma(61, "Vice"), tma(62, "Head")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'vice', 0), (1, ?, 'head', 0), (1, ?, 'member', 0)",
                (vice["id"], head["id"], mem["id"]))
    con.commit()
    sent = lambda: sorted(r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = 'important'"))  # noqa: E731
    post = {"title": "Meeting moved to 305", "body": "", "tag": "important"}
    assert c.post("/api/orgs/1/posts", headers=H, json=post).status_code == 403            # Head can't
    pid = c.post("/api/orgs/1/posts", headers=H, json={**post, "tag": "news"}).json()["id"]
    assert sent() == []                                                                    # a plain post is silent
    assert c.patch(f"/api/posts/{pid}", headers=H, json={"tag": "important"}).status_code == 403
    c.post("/api/orgs/1/posts", headers=V, json=post)
    assert sent() == sorted([head["id"], mem["id"]])
    c.post("/api/orgs/1/posts", headers=V, json={**post, "title": "And again"})
    assert len(sent()) == 2                                                                # once a day per club
    m = con.execute("SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'important' AND b.user_id = ?", (mem["id"],)).fetchone()
    text, button, start = bot._render(con, m)
    assert "IT Club" in text and "Meeting moved to 305" in text and start == "news"


def test_official_roles(env):
    """Every club has the three official roles: the President (the level) and the fixed Vice
    and Head, which can't be renamed, deleted or raised (their rights below the level may be tuned); a Vice or Head
    without a role name holds them, the old President too after handing the club over."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "vic"), (22, "hed")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22)}
    for tg, role in ((20, "president"), (21, "vice"), (22, "head")):
        logic.set_role(con, None, ids[tg], oid, role, "test")
    roles = c.get(f"/api/orgs/{oid}/team", headers=tma(20)).json()["roles"]
    assert [(r["name"], r["level"], r["fixed"], r["count"]) for r in roles] == [("Vice", "vice", True, 1), ("Head", "head", True, 1)]
    vp, head = roles[0]["id"], roles[1]["id"]
    assert c.delete(f"/api/orgs/{oid}/roles/{head}", headers=tma(20)).status_code == 403
    assert c.patch(f"/api/orgs/{oid}/roles/{head}", headers=tma(20), json={"name": "Boss", "color": "#2FBF71", "rights": ["money"]}).status_code == 403
    out = c.patch(f"/api/orgs/{oid}/roles/{head}", headers=tma(21), json={"name": "Boss", "color": "#2FBF71", "rights": ["door", "events"]}).json()["roles"]
    assert next((r["name"], r["level"], r["rights"]) for r in out if r["id"] == head) == ("Head", "head", ["door", "events"])
    c.post(f"/api/orgs/{oid}/transfer", headers=tma(20), json={"userId": ids[21]})
    assert con.execute("SELECT role, role_id FROM org_members WHERE org_id = ? AND user_id = ?", (oid, ids[20])).fetchone()[:] == ("vice", vp)
    # a clubmate sees the role; outside the club, the card shows no clubs at all since audit M2 (it showed the club, not the role)
    login(c, 30, "out")
    clubs = lambda viewer: c.get(f"/api/users/{ids[21]}", headers=tma(viewer)).json()["clubs"]  # noqa: E731
    assert clubs(30) == [] and next(m for m in clubs(22) if m["org"]["id"] == oid)["role"] == "president"


def test_volunteers(env):
    """Volunteers: an event asks for N, maybe not year 1; a student applies with a "why", the organizer
    says yes or no and the bot tells them; no more yeses than places."""
    c, cfg = env
    for uid, name in ((20, "pres"), (21, "ali"), (22, "bota"), (23, "dan")):
        login(c, uid, name)
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    ids = {tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0] for tg in (20, 21, 22, 23)}
    logic.set_role(con, None, ids[20], oid, "president", "test")
    con.execute("UPDATE students SET course = 1, student_id = printf('%02dB%07d', ?, user_id) WHERE user_id = ?", (INTAKE % 100, ids[23]))
    ev = {"title": "Open day", "place": "Atrium", "startsAt": int(time.time()) + 7 * 86400, "emoji": "crown_3d", "color": "#3B6BFF",
          "seats": 50, "volunteers": 1, "volunteersSenior": True}
    e = c.post(f"/api/orgs/{oid}/events", headers=tma(20), json=ev).json()
    assert c.post(f"/api/events/{e['id']}/publish", headers=tma(20)).status_code == 200
    assert c.post(f"/api/events/{e['id']}/volunteer", headers=tma(23), json={}).status_code == 403          # year 1
    r = c.post(f"/api/events/{e['id']}/volunteer", headers=tma(21), json={"note": "I helped last year"}).json()
    assert r["volunteers"]["mine"] == "asked" and "asked" not in r["volunteers"]                              # a student sees no counts of others waiting
    assert c.post(f"/api/events/{e['id']}/volunteer", headers=tma(22), json={}).status_code == 200
    assert c.get(f"/api/events/{e['id']}/volunteers", headers=tma(21)).status_code == 403
    lst = c.get(f"/api/events/{e['id']}/volunteers", headers=tma(20)).json()
    assert [x["note"] for x in lst] == ["I helped last year", ""] and lst[0]["fullName"]
    assert c.put(f"/api/events/{e['id']}/volunteers/{ids[21]}", headers=tma(20), json={"yes": True}).status_code == 200
    assert c.put(f"/api/events/{e['id']}/volunteers/{ids[22]}", headers=tma(20), json={"yes": True}).status_code == 409   # one place
    assert c.put(f"/api/events/{e['id']}/volunteers/{ids[22]}", headers=tma(20), json={"yes": False}).status_code == 200
    assert {r[0] for r in con.execute("SELECT kind FROM bot_outbox WHERE kind LIKE 'volunteer_%'")} == {"volunteer_yes", "volunteer_no"}
    c.delete(f"/api/events/{e['id']}/volunteer", headers=tma(22))                                            # a "no" can't be undone
    c.post(f"/api/events/{e['id']}/volunteer", headers=tma(22), json={})                                     # by leaving and applying again
    assert con.execute("SELECT status FROM volunteers WHERE event_id = ? AND user_id = ?", (e["id"], ids[22])).fetchone()[0] == "no"
    assert c.get(f"/api/events/{e['id']}", headers=tma(20)).json()["volunteers"] == {"need": 1, "senior": True, "taken": 1, "mine": None, "asked": 0}


def test_club_short_links(env):
    """A5: a club's slug comes from its name (Cyrillic in Latin letters, unique, never the app's own paths); only the
    President changes it; kbtu.sow.kz/<slug> opens the club in the bot; the clubs made before take their names' slugs."""
    c, cfg = env
    pres, vice = login(c, 90, "pres"), login(c, 91, "vice")
    con = db.connect(cfg.db_path)
    with db.tx(con):
        a = logic.create_org(con, None, "\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439 \u043a\u043b\u0443\u0431", "SK", "trophy_3d", False)
        b = logic.create_org(con, None, "\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439  \u041a\u043b\u0443\u0431!", "SK", "trophy_3d", False)
        x = logic.create_org(con, None, "API", "A", "trophy_3d", False)
        old = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('club7', 'club', 'Open Mic', 'OM', 'trophy_3d', 0)").lastrowid
    slug = lambda oid: con.execute("SELECT slug FROM orgs WHERE id = ?", (oid,)).fetchone()[0]  # noqa: E731
    assert (slug(a), slug(b), slug(x)) == ("shahmatnyiklub", "shahmatnyiklub2", "api2")
    con.execute("DELETE FROM meta WHERE key = 'slugs_named'")  # the app's start ran it already
    logic.name_slugs(con)
    assert slug(old) == "openmic"
    con.execute("UPDATE orgs SET slug = 'club7' WHERE id = ?", (old,))
    logic.name_slugs(con)
    assert slug(old) == "club7"                                                        # once: a chosen club7 stays
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0), (?, ?, 'vice', 0)", (a, pres["id"], a, vice["id"]))
    P = tma(90, "Pres")
    assert c.patch(f"/api/orgs/{a}", headers=tma(91, "Vice"), json={"slug": "chess"}).status_code == 403   # the President's
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "exit"}).status_code == 400                  # the app's own
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "Ch-ess"}).status_code == 400
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "club7"}).status_code == 409
    assert c.patch(f"/api/orgs/{a}", headers=P, json={"slug": "Chess"}).json()["slug"] == "chess"
    r = c.get("/Chess", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith(f"?startapp=cl_{a}")
    assert c.get("/shahmatnyiklub", follow_redirects=False).headers["location"].endswith(f"cl_{a}")  # the old bio still works
    assert logic.slug_for(con, "Shahmatnyi klub") == "shahmatnyiklub3"                 # and nobody else takes it
    assert c.get("/nosuchclub", follow_redirects=False).status_code == 200                              # the app itself
    assert c.get("/exit", follow_redirects=False).headers["location"].endswith("startapp=exit")


def test_custom_short_links(env):
    """A club's Vice+ makes kbtu.sow.kz/<slug> for the club, one of its published events or its round, never outside the
    app; names are first come, first served across club slugs and links, never the app's own; DMP's admin revokes any."""
    c, cfg = env
    ids = {n: login(c, i, n)["id"] for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "other"), (24, "boss"))}
    H = {n: tma(i, n.title()) for i, n in ((20, "pres"), (21, "vice"), (22, "head"), (23, "other"), (24, "boss"))}
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', 'Chess', 'CH', 'trophy_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, ids["pres"], "president"), (1, ids["vice"], "vice"), (1, ids["head"], "head"), (2, ids["other"], "president")])
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (ids["boss"],))
    start = int(time.time()) + 3600
    ev = c.post("/api/orgs/1/events", headers=H["pres"], json={"seats": None, "title": "Hack night", "place": "305", "startsAt": start, "endsAt": start + 7200,
                                                                "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    add = lambda who, body, org=1: c.post(f"/api/orgs/{org}/links", headers=H[who], json=body)  # noqa: E731
    assert add("head", {"slug": "join-it", "kind": "club"}).status_code == 403                  # Vice and above
    assert add("other", {"slug": "join-it", "kind": "club"}).status_code == 403                 # someone else's club
    assert add("vice", {"slug": "hack", "kind": "event", "eventId": ev["id"]}).status_code == 400  # a draft
    c.post(f"/api/events/{ev['id']}/publish", headers=H["pres"])
    other = c.post("/api/orgs/2/events", headers=H["other"], json={"seats": None, "title": "Blitz", "place": "305", "startsAt": start, "endsAt": start + 60,
                                                                    "emoji": "trophy_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{other['id']}/publish", headers=H["other"])
    assert add("vice", {"slug": "blitz", "kind": "event", "eventId": other["id"]}).status_code == 400  # another club's event
    for bad in ("a", "-it", "it-", "i--t", "\u0430\u0431\u0432", "x" * 33, "it/../x", "https://evil.example"):
        assert add("vice", {"slug": bad, "kind": "club"}).status_code == 400, bad
    assert add("vice", {"slug": "evil", "kind": "url", "url": "https://evil.example"}).status_code == 400  # only into the app
    for taken in ("admin", "api", "login", "assets", "static", "privacy", "chess"):              # the app's own, a club's slug
        assert add("vice", {"slug": taken, "kind": "club"}).json()["message"] == "taken", taken
    assert add("vice", {"slug": "Join-IT", "kind": "club"}).status_code == 200
    assert add("vice", {"slug": "hack-night", "kind": "event", "eventId": ev["id"]}).status_code == 200
    got = add("pres", {"slug": "it-casting", "kind": "round"}).json()
    assert {(x["slug"], x["kind"], x["eventTitle"]) for x in got} == {("join-it", "club", None), ("hack-night", "event", "Hack night"), ("it-casting", "round", None)}
    assert add("other", {"slug": "join-it", "kind": "club"}, 2).json()["message"] == "taken"   # first come, first served
    assert c.patch("/api/orgs/2", headers=H["other"], json={"slug": "hacknight"}).status_code == 200
    assert add("vice", {"slug": "hacknight", "kind": "club"}).json()["message"] == "taken"      # nor a club's slug
    assert logic.slug_for(con, "Join") == "join" and not logic._slug_free(con, "join-it", None)
    assert c.get("/api/orgs/1/links", headers=H["head"]).status_code == 403
    go = lambda p: c.get(p, follow_redirects=False).headers.get("location", "")  # noqa: E731
    assert go("/join-it").endswith("?startapp=cl_1") and go("/HACK-NIGHT").endswith(f"?startapp=ev_{ev['id']}") and go("/it-casting").endswith("?startapp=rc_1")
    assert go("/it").endswith("?startapp=cl_1")                                                   # the club's slug as before
    # its own Vice takes one down; another club can't; the admin revokes any, and the log says which
    assert c.delete("/api/links/join-it", headers=H["other"]).status_code == 403
    assert c.delete("/api/links/join-it", headers=H["vice"]).status_code == 204
    assert go("/join-it").endswith("?startapp=cl_1")                                             # its posters open the club now
    assert add("other", {"slug": "join-it", "kind": "club"}, 2).json()["message"] == "taken"   # never another club's
    assert "it-casting" in next(o for o in c.get("/api/admin/orgs", headers=H["boss"]).json() if o["id"] == 1)["shortLinks"]
    assert c.delete("/api/links/it-casting", headers=H["boss"]).status_code == 204
    assert c.delete("/api/links/it-casting", headers=H["boss"]).status_code == 404
    assert [r[0] for r in con.execute("SELECT action FROM audit_log WHERE action LIKE 'link_%' ORDER BY id")] == ["link_create"] * 3 + ["link_delete", "link_revoke"]
    # a deleted event takes its link along; a hidden club's links lead nowhere
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = 1")
    assert c.get("/hack-night", follow_redirects=False).status_code == 200
    con.execute("DELETE FROM events WHERE id = ?", (ev["id"],))
    assert not con.execute("SELECT 1 FROM short_links WHERE slug = 'hack-night'").fetchone()
    # an event deleted in the app keeps its link's name for its club, which may take it again
    con.execute("UPDATE orgs SET status = 'active' WHERE id = 1")
    ev2 = c.post("/api/orgs/1/events", headers=H["pres"], json={"seats": None, "title": "Draft", "place": "305", "startsAt": start, "endsAt": start + 60,
                                                                 "emoji": "laptop_3d", "color": "#3B6BFF"}).json()
    c.post(f"/api/events/{ev2['id']}/publish", headers=H["pres"])
    assert add("vice", {"slug": "draft-ev", "kind": "event", "eventId": ev2["id"]}).status_code == 200
    con.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (ev2["id"],))
    assert c.delete(f"/api/events/{ev2['id']}", headers=H["pres"]).status_code in (200, 204)
    assert add("other", {"slug": "draft-ev", "kind": "club"}, 2).json()["message"] == "taken"
    assert add("vice", {"slug": "draft-ev", "kind": "club"}).status_code == 200
    assert logic.kz_phone("\u0667\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668") is None    # Arabic-Indic digits
    assert logic.kz_phone("+7 701 234 56 7") is None and logic.kz_phone("701 234 56 78") == "+77012345678"
    assert logic.kz_phone("8 (701) 234-56-78") == logic.kz_phone("+7 701 234 5678") == "+77012345678"


def test_club_people(env):
    """Members are public: President and Vice on the club, everyone behind a button; a club may hide the list."""
    c, cfg = env
    pres, vice, ali, bob = login(c, 70, "pres"), login(c, 71, "vice"), login(c, 72, "ali"), login(c, 73, "bob")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    for u, role in ((pres, "president"), (vice, "vice"), (ali, "member")):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", (u["id"], role))
    o = c.get("/api/orgs/1", headers=tma(73)).json()
    assert [m["role"] for m in o["leaders"]] == ["president", "vice"] and o["membersHidden"] is False
    everyone = c.get("/api/orgs/1/people", headers=tma(73)).json()
    assert [m["person"]["id"] for m in everyone] == [pres["id"], vice["id"], ali["id"]] and "username" not in everyone[0]
    assert c.patch("/api/orgs/1", headers=tma(72), json={"membersHidden": True}).status_code == 403   # a member can't
    assert c.patch("/api/orgs/1", headers=tma(70), json={"membersHidden": True}).json()["membersHidden"] is True
    assert c.get("/api/orgs/1/people", headers=tma(73)).status_code == 403                             # a stranger now can't
    assert len(c.get("/api/orgs/1/people", headers=tma(72)).json()) == 3                               # its own people can
    assert len(c.get("/api/orgs/1", headers=tma(73)).json()["leaders"]) == 2                           # the leaders still show


def test_club_abbr(env):
    """A club's short name: the clubs made before take their initials at start and keep a set one; a new
    club has its initials from the first day; Vice+ edit it (one word, 2-8 characters), a member can't; DMP and the
    admin may set any club's, and only that."""
    c, cfg = env
    pres, vice, ali, dmp, boss = (login(c, 70 + i, n) for i, n in enumerate(("pres", "vice", "ali", "dmp", "boss")))
    con = db.connect(cfg.db_path)
    film = "\u041a\u043b\u0443\u0431 \u043a\u0438\u043d\u043e \u0438 \u0442\u0435\u0430\u0442\u0440\u0430"  # "Club of film and theatre" in Russian
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic Club of KBTU', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'film', 'club', ?, 'F', 'popcorn_3d', 0)", (film,))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, abbr, emoji, created_at) VALUES (3, 'go', 'club', 'Go Club', 'G', 'Baduk', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (9, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, pres["id"], "president"), (1, vice["id"], "vice"), (1, ali["id"], "member"), (9, dmp["id"], "head")])
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    logic.fill_abbrs(con)
    logic.fill_abbrs(con)   # every start: nothing left to fill
    assert [r[0] for r in con.execute("SELECT abbr FROM orgs WHERE id IN (1, 2, 3) ORDER BY id")] == ["OMC", "\u041a\u041a\u0422", "Baduk"]
    assert logic.initials("Studex") == "STUDEX" and logic.initials("The Club") == "CLUB"
    assert con.execute("SELECT abbr FROM orgs WHERE id = ?", (logic.create_org(con, None, "Robotics and AI Society", "R", "laptop_3d", False),)).fetchone()[0] == "RAS"

    patch = lambda uid, body: c.patch("/api/orgs/1", headers=tma(uid), json=body)  # noqa: E731
    assert c.get("/api/orgs/1", headers=tma(72)).json()["abbr"] == "OMC"
    assert patch(72, {"abbr": "MIC"}).status_code == 403                         # a member can't
    assert patch(71, {"abbr": "MIC"}).json()["abbr"] == "MIC"                    # the Vice can
    for bad in ("M", "TOO LONG", "NINECHARS", ""):
        assert patch(70, {"abbr": bad}).status_code == 400, bad
    assert patch(73, {"abbr": "OMC"}).json()["abbr"] == "OMC"                    # DMP on any club
    assert patch(73, {"abbr": "OMC", "name": "Mic Night"}).status_code == 403    # and nothing else
    assert patch(74, {"abbr": "MIC"}).json()["abbr"] == "MIC"                    # the admin too


def test_membership_oversee(env):
    """DMP is an org in Studio: a membership says whether I lead in an overseeing org, so Studio shows
    the registry with it picked; a plain member of DMP, or a club's Vice, doesn't get it."""
    c, cfg = env
    dana, ali = login(c, 90, "dana"), login(c, 91, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, can_oversee, created_at) VALUES (1, 'dmp', 'office', 'DMP', 'D', 'trophy_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)",
                    [(1, dana["id"], "head"), (2, dana["id"], "vice"), (1, ali["id"], "member")])
    mine = {m["org"]["id"]: m["oversee"] for m in c.get("/api/me", headers=tma(90)).json()["memberships"]}
    assert mine == {1: True, 2: False} and c.get("/api/me", headers=tma(90)).json()["oversee"] is True
    assert [m["oversee"] for m in c.get("/api/me", headers=tma(91)).json()["memberships"]] == [False]


def test_student_government_mark(env):
    """The Student Government: a mark and first in the clubs list, no rights beyond any club's."""
    c, cfg = env
    login(c, 31, "student")
    h = tma(31)
    con = db.connect(cfg.db_path)
    big = logic.create_org(con, None, "Chess Club", "CH", "trophy_3d", True, "chess")
    gov = logic.create_org(con, None, "Student Government", "SG", "trophy_3d", True, logic.GOV_SLUG)
    con.execute("INSERT INTO subscriptions (user_id, org_id, created_at) SELECT id, ?, 0 FROM users", (big,))
    login(c, 32, "o1")
    login(c, 33, "o2")
    for o in (big, gov):  # a club of one isn't listed
        con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT ?, id, 'member', 0 FROM users WHERE tg_id = ?", [(o, 32), (o, 33)])
    con.close()
    found = [o for o in c.get("/api/orgs", headers=h).json() if o["id"] in (big, gov)]
    assert [(o["id"], o.get("gov")) for o in found] == [(gov, True), (big, None)]   # first though followed less
    g = c.get(f"/api/orgs/{gov}", headers=h).json()
    assert g["gov"] is True and not g.get("canOversee") and g["myRole"] is None


def test_org_names(env):
    """Org names, one style: "KBTU" and "Club" off either end on create and rename, an acronym the name carried
    goes to the abbr (in brackets, or before a dash), else the initials without "KBTU"."""
    import dataclasses
    for typed, name, abbr in [("KBTU Open Mic", "Open Mic", "OM"), ("Debate Club | kbtu", "Debate", "DC"),
                              ("IEEE KBTU Chapter", "IEEE", "IEEE"), ("AIESEC in KBTU", "AIESEC", "AIESEC"),
                              ("KBTU’s Music Club", "Music", "MC"), ("Society of Petroleum Engineers (SPE)", "Society of Petroleum Engineers", "SPE"),
                              ("SPE – Society of Petroleum Engineers", "Society of Petroleum Engineers", "SPE"),
                              ("Chess (beginners)", "Chess (beginners)", "CB"), ("Data KBTU Club", "Data", "DC"), ("Japanese Culture Club KBTU", "Japanese Culture", "JCC"),
                              ("\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439 \u043a\u043b\u0443\u0431", "\u0428\u0430\u0445\u043c\u0430\u0442\u043d\u044b\u0439 \u043a\u043b\u0443\u0431", "\u0428\u041a"),
                              ("\u041a\u043b\u0443\u0431 \u00ab\u0414\u0435\u0431\u0430\u0442\u044b\u00bb", "\u0414\u0435\u0431\u0430\u0442\u044b", "\u041a\u0414"), ("Club", "Club", "CLUB"),
                              ("3D Printing (KBTU)", "3D Printing", "3P"), ("KBTU", "KBTU", "KBTU"),
                              ("\u041a\u0411\u0422\u0423 \u0414\u0435\u0431\u0430\u0442\u044b", "\u0414\u0435\u0431\u0430\u0442\u044b", "\u0414\u0415\u0411\u0410\u0422\u042b")]:
        assert (logic.org_name(typed)[0], logic.guess_abbr(typed)) == (name, abbr), typed
    _, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, admins=frozenset({20}))))
    A = tma(20)
    c.get("/api/me", headers=A)
    club = c.post("/api/admin/orgs", headers=A, json={"name": "KBTU Society of Petroleum Engineers (SPE)", "short": "sp", "emoji": "trophy_3d"}).json()
    assert (club["name"], club["abbr"], club["slug"]) == ("Society of Petroleum Engineers", "SPE", "societyofpetroleumengi")
    login(c, 21, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT ?, id, 'president', 0 FROM users WHERE tg_id = 21", (club["id"],))
    con.close()
    def edit(body):
        assert c.patch(f"/api/orgs/{club['id']}", headers=tma(21), json=body).status_code == 200
        o = c.get(f"/api/orgs/{club['id']}", headers=tma(21)).json()
        return o["name"], o["abbr"]
    assert edit({"name": "Petroleum KBTU"}) == ("Petroleum", "SPE")                  # renamed: the abbr it had stays
    assert edit({"name": "PC \u2013 Petroleum"}) == ("Petroleum", "PC")    # one the new name carries
    assert edit({"name": "KBTU Oil (OC)", "abbr": "Oil"}) == ("Oil", "Oil")  # an abbr sent with it wins


def test_club_rename_review3(env):
    """Review 3: a club's own "Club" survives the next start (fill_abbrs cut it again at every start); a rename takes
    no other org's name in other letters or case, no KBTU alone or in look-alike letters, no check mark."""
    c, cfg = env
    pres = login(c, 21, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'phys', 'club', 'Physics', 'P', 'laptop_3d', 1, 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (2, 'chess', 'club', '\u0428\u0430\u0445\u043c\u0430\u0442\u044b', 'C', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (3, 'go', 'club', 'Go', 'G', 'laptop_3d', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (4, 'cheer', 'club', 'Cheerleading', 'C', 'laptop_3d', 1, 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0)", [(o, pres["id"]) for o in (1, 3, 4)])
    rename = lambda oid, name: c.patch(f"/api/orgs/{oid}", headers=tma(21), json={"name": name})  # noqa: E731
    assert rename(3, "Go Club").json()["message"] == "club_word"               # owner, Nov 3: no "Club" in a name
    con.execute("UPDATE orgs SET name = 'Go Club' WHERE id = 3")              # one named before stays
    logic.fill_abbrs(con)                                                      # the next deploy's start
    assert con.execute("SELECT name FROM orgs WHERE id = 3").fetchone()[0] == "Go Club"
    for name in ("KBTU", "\u041a\u0412\u0422\u0423 Go", "\uff2b\uff22\uff34\uff35 Go", "K.B.T.U. Go", "Go \u2705"):
        assert rename(3, name).status_code == 400, name                       # KBTU look-alikes, a fake badge
    for name in ("\u0448\u0430\u0445\u043c\u0430\u0442\u044b", "\u0428\u0410\u0425\u041c\u0410\u0422\u042b", "\u0420hysics", "physics."):
        assert rename(3, name).json()["message"] == "taken", name             # another club's, in other case or letters
    assert rename(4, "Cheerleading Club").status_code == 403 and rename(1, "Physics Lab").status_code == 403  # official: DMP's
    assert rename(1, "Physics").status_code == 200                            # unchanged: no check
