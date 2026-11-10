"""A club's members mirrored from its Telegram chats (logic/chatsync.py, CHAT_SYNC=1): chat_member joins and leaves,
the President kept, pauses (the bot not an admin, a Telegram error, an implausible drop), departments as a set, a
manual removal respected, the dry run's counts, a resumed sweep, the nightly look, the switch, deleting an account."""
from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from kbtu import app as server, bot, db, logic
from kbtu.logic import chatsync
from test_core import delete_now, login, tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)

MAIN, DEPT, DEPT2, BOT_ID = -1001, -1002, -1003, 4242
P, V = 9, 8  # the President, a Vice (Telegram ids; login makes the accounts)


@pytest.fixture
def club(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    monkeypatch.setattr(chatsync, "POLICY", "pol")
    org = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('senate', 'club', 'SITE Senate', 'S', 'trophy_3d', 0)").lastrowid
    for tg, name, role in ((P, "pres", "president"), (V, "vic", "vice")):
        login(c, tg, name)
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", (org, uid(con, tg), role))
    for tg, name in ((1, "ann"), (2, "bob"), (3, "cat"), (4, "dan"), (5, "eve"), (6, "fay")):
        login(c, tg, name)
    con.execute("UPDATE students SET consent_version = 'pol'")
    for name in ("Media", "Events"):
        con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, ?, '#3B6BFF', 1, 0)", (org, name))
    chatsync.link(con, "senate", MAIN, "main")
    chatsync.link(con, "senate", DEPT, "dept", "media")
    chatsync.link(con, "senate", DEPT2, "dept", "Events")
    yield c, cfg, con, org
    con.close()


def uid(con, tg):
    return con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]


def tag(con, name):
    return con.execute("SELECT id FROM org_tags WHERE name = ?", (name,)).fetchone()[0]


def role(con, org, tg):
    r = con.execute("SELECT role FROM org_members WHERE org_id = ? AND user_id = ?", (org, uid(con, tg))).fetchone()
    return r and r[0]


def upd(chat, tg, old, new, date=None, **extra):
    return {"chat": {"id": chat, "type": "supergroup"}, "from": {"id": tg}, "date": date or logic.core.now() + 1,
            "old_chat_member": {"status": old, "user": {"id": tg, "is_bot": False}},
            "new_chat_member": {"status": new, "user": {"id": tg, "is_bot": False}, **extra}}


def tg_api(inside: dict, bot_status="administrator", errors=None):
    """A fake getChatMember: `inside` maps a Telegram id to its status (absent: left)."""
    calls = []

    async def call(method, params):
        calls.append(params["user_id"])
        if params["user_id"] == BOT_ID:
            return {"ok": True, "result": {"status": bot_status}}
        if errors and params["user_id"] in errors:
            return {"ok": False, "error_code": 400, "description": errors[params["user_id"]]}
        return {"ok": True, "result": {"status": inside.get(params["user_id"], "left")}}
    call.calls = calls
    return call


def sweep(con, call, n=chatsync.STEP):
    while asyncio.run(chatsync.step(con, call, BOT_ID, n)):
        pass


def test_join_leave_kick(club):
    c, cfg, con, org = club
    chatsync.member_update(con, upd(MAIN, 1, "left", "member"))
    assert role(con, org, 1) == "member"
    line = con.execute("SELECT actor_id, data FROM audit_log WHERE action = 'role_change' AND target = ?", (f"user:{uid(con, 1)}",)).fetchone()
    assert line[0] is None and json.loads(line[1]) == {"org": org, "role": "member", "by": "sync", "sync": MAIN}
    chatsync.member_update(con, upd(MAIN, 2, "left", "restricted", is_member=True))  # restricted, still a member
    chatsync.member_update(con, upd(MAIN, 3, "left", "restricted", is_member=False))
    assert role(con, org, 2) == "member" and role(con, org, 3) is None
    chatsync.member_update(con, upd(MAIN, 1, "member", "administrator"))  # a change inside the chat: nothing
    assert role(con, org, 1) == "member"
    chatsync.member_update(con, upd(MAIN, 1, "member", "left"))
    chatsync.member_update(con, upd(MAIN, 2, "member", "kicked"))
    assert role(con, org, 1) is None and role(con, org, 2) is None
    gone = json.loads(con.execute("SELECT data FROM audit_log WHERE action = 'role_change' AND target = ? ORDER BY id DESC", (f"user:{uid(con, 1)}",)).fetchone()[0])
    assert gone == {"org": org, "role": "none", "by": "sync", "sync": MAIN}
    chatsync.member_update(con, upd(MAIN, 1, "left", "member", date=logic.core.now() + 5))  # rejoins: back (the sync's removal holds nothing)
    assert role(con, org, 1) == "member"
    # strangers, bots, staff, the typed-in, those not on the policy in force: nothing, and nothing stored
    n = con.execute("SELECT COUNT(*) FROM org_members").fetchone()[0]
    chatsync.member_update(con, upd(MAIN, 777, "left", "member"))
    bot_upd = upd(MAIN, 4, "left", "member")
    bot_upd["new_chat_member"]["user"]["is_bot"] = True
    chatsync.member_update(con, bot_upd)
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (uid(con, 5),))
    con.execute("UPDATE students SET consent_version = '1' WHERE user_id = ?", (uid(con, 6),))
    chatsync.member_update(con, upd(MAIN, 5, "left", "member"))
    chatsync.member_update(con, upd(MAIN, 6, "left", "member"))
    chatsync.member_update(con, upd(-999, 4, "left", "member"))  # a chat nobody linked
    assert con.execute("SELECT COUNT(*) FROM org_members").fetchone()[0] == n
    assert not con.execute("SELECT 1 FROM users WHERE tg_id = 777").fetchone()


def test_president_kept(club):
    c, cfg, con, org = club
    chatsync.member_update(con, upd(MAIN, P, "creator", "left"))
    assert role(con, org, P) == "president"
    sweep(con, chatsync_start(con, MAIN, True, tg_api({V: "member"})))
    assert role(con, org, P) == "president" and role(con, org, V) == "vice"


def chatsync_start(con, chat, apply, call):
    assert chatsync.start(con, chat, apply)
    return call


def test_paused_when_the_bot_loses_admin(club):
    c, cfg, con, org = club
    chatsync.member_update(con, upd(MAIN, 1, "left", "member"))
    chatsync.bot_status(con, MAIN, "member")  # demoted
    assert con.execute("SELECT paused FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0]
    chatsync.member_update(con, upd(MAIN, 1, "member", "left"))
    assert role(con, org, 1) == "member"  # paused: no removals at all
    chatsync.bot_status(con, MAIN, "administrator")  # promoted again: still paused until the creator runs it
    assert con.execute("SELECT paused FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0]
    # a sweep that finds the bot no admin, or Telegram refusing, pauses too and removes nobody
    sweep(con, chatsync_start(con, MAIN, True, tg_api({}, bot_status="member")))
    assert "not an admin" in con.execute("SELECT paused FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0] and role(con, org, 1) == "member"
    sweep(con, chatsync_start(con, MAIN, True, tg_api({}, errors={1: "Bad Request: chat not found"})))
    assert "getChatMember" in con.execute("SELECT paused FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0] and role(con, org, 1) == "member"
    assert not con.execute("SELECT 1 FROM chat_sync_todo").fetchone()
    # the bot in the my_chat_member path pauses it as well
    chatsync.start(con, DEPT, False)
    asyncio.run(bot._member(dataclasses.replace(cfg), None, con, {"chat": {"id": DEPT, "type": "group"}, "new_chat_member": {"status": "kicked"}}))
    assert con.execute("SELECT paused FROM chat_sync WHERE chat_id = ?", (DEPT,)).fetchone()[0]


def test_implausible_drop_pauses(club):
    c, cfg, con, org = club
    for tg in (1, 2, 3, 4, 5):
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, uid(con, tg)))
    sweep(con, chatsync_start(con, MAIN, True, tg_api({P: "creator", V: "member"})))  # 5 of 7 "left"
    paused = con.execute("SELECT paused, result FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()
    assert "implausible" in paused[0] and "5 of 7" in paused[1]
    assert all(role(con, org, tg) == "member" for tg in (1, 2, 3, 4, 5))
    sweep(con, chatsync_start(con, MAIN, True, tg_api({P: "creator", V: "member", 1: "member", 2: "member", 3: "member"})))  # 2 of 7: plausible
    assert role(con, org, 4) is None and role(con, org, 5) is None and role(con, org, 1) == "member"


def test_departments_a_set(club):
    c, cfg, con, org = club
    media, events = tag(con, "Media"), tag(con, "Events")
    chatsync.member_update(con, upd(DEPT, 1, "left", "member"))  # not in the club: no department
    assert not con.execute("SELECT 1 FROM member_tags WHERE user_id = ?", (uid(con, 1),)).fetchone()
    chatsync.member_update(con, upd(MAIN, 1, "left", "member"))
    chatsync.member_update(con, upd(DEPT, 1, "left", "member", date=logic.core.now() + 2))
    chatsync.member_update(con, upd(DEPT2, 1, "left", "member", date=logic.core.now() + 2))
    assert logic.depts_of(con, org, uid(con, 1)) == sorted([media, events])
    assert con.execute("SELECT sync FROM member_tags WHERE user_id = ? AND tag_id = ?", (uid(con, 1), media)).fetchone()[0] == 1
    chatsync.member_update(con, upd(DEPT2, 1, "member", "left"))
    assert logic.depts_of(con, org, uid(con, 1)) == [media]  # the other stays
    # a Head whose department came by sync manages nothing by it
    con.execute("UPDATE org_members SET role = 'head' WHERE user_id = ?", (uid(con, 1),))
    assert logic.depts_of(con, org, uid(con, 1), own=True) == []
    chatsync.member_update(con, upd(MAIN, 1, "member", "left"))  # out of the club: its departments go too
    assert role(con, org, 1) is None and logic.depts_of(con, org, uid(con, 1)) == []


def test_manual_removal_respected(club):
    c, cfg, con, org = club
    chatsync.member_update(con, upd(MAIN, 1, "left", "member"))
    assert c.post(f"/api/orgs/{org}/members/{uid(con, 1)}/remove", headers=tma(P), json={}).json() == {"done": True}
    sweep(con, chatsync_start(con, MAIN, True, tg_api({P: "creator", V: "member", 1: "member"})))  # still in the chat
    assert role(con, org, 1) is None
    removed = con.execute("SELECT MAX(at) FROM audit_log WHERE action = 'role_change'").fetchone()[0]
    chatsync.member_update(con, upd(MAIN, 1, "left", "member", date=removed))  # an update from before the removal
    assert role(con, org, 1) is None
    chatsync.member_update(con, upd(MAIN, 1, "left", "member", date=removed + 1))  # joined the chat again after it
    assert role(con, org, 1) == "member"
    # a department taken by hand: the same
    media = tag(con, "Media")
    chatsync.member_update(con, upd(DEPT, 1, "left", "member", date=removed + 2))
    assert c.patch(f"/api/orgs/{org}/members/{uid(con, 1)}", headers=tma(V), json={"dropDept": media}).status_code == 200
    sweep(con, chatsync_start(con, DEPT, True, tg_api({1: "member"})))
    assert logic.depts_of(con, org, uid(con, 1)) == []
    # banned: never back, whatever the chat says
    assert c.post(f"/api/orgs/{org}/members/{uid(con, 1)}/remove", headers=tma(P), json={"ban": True}).status_code == 200
    chatsync.member_update(con, upd(MAIN, 1, "left", "member", date=logic.core.now() + 99))
    assert role(con, org, 1) is None


def test_dry_run_counts_and_apply(club):
    c, cfg, con, org = club
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, uid(con, 4)))
    inside = {P: "creator", V: "member", 1: "member", 2: "administrator", 777: "member"}  # 777: no account
    sweep(con, chatsync_start(con, MAIN, False, tg_api(inside)))
    assert con.execute("SELECT result FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0] == "dry run: would add 2, would remove 1"
    assert role(con, org, 1) is None and role(con, org, 4) == "member" and not con.execute("SELECT 1 FROM chat_sync_todo").fetchone()
    call = tg_api(inside)
    sweep(con, chatsync_start(con, MAIN, True, call))
    assert con.execute("SELECT result FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0] == "apply: added 2, removed 1"
    assert role(con, org, 1) == role(con, org, 2) == "member" and role(con, org, 4) is None
    assert 777 not in call.calls  # only app users are asked about


def test_sweep_resumes(club):
    c, cfg, con, org = club
    chatsync.start(con, MAIN, True)
    call = tg_api({P: "creator", V: "member", 1: "member", 2: "member", 3: "member"})
    assert asyncio.run(chatsync.step(con, call, BOT_ID, 3))  # a few, then "a restart"
    pos = con.execute("SELECT sweep_pos FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0]
    assert pos and con.execute("SELECT sweep FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0] == "apply"
    sweep(con, call, 3)
    assert all(role(con, org, tg) == "member" for tg in (1, 2, 3))
    asked = [x for x in call.calls if x != BOT_ID]
    assert len(asked) == len(set(asked))  # nobody asked twice


def test_night_looks_at_members_only(club):
    c, cfg, con, org = club
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, uid(con, 4)))
    chatsync.night(con)
    assert con.execute("SELECT COUNT(*) FROM chat_sync WHERE sweep = 'night'").fetchone()[0] == 3
    call = tg_api({P: "creator", V: "member", 1: "member"})
    sweep(con, call)
    assert role(con, org, 1) is None and role(con, org, 4) is None  # a non-member isn't added; a member gone is removed
    assert set(call.calls) - {BOT_ID} <= {P, V, 4}


def test_off_without_the_switch(club, monkeypatch):
    c, cfg, con, org = club
    monkeypatch.setattr(chatsync, "POLICY", "")
    chatsync.member_update(con, upd(MAIN, 1, "left", "member"))
    chatsync.start(con, MAIN, True)
    assert role(con, org, 1) is None and not asyncio.run(chatsync.step(con, tg_api({1: "member"}), BOT_ID))
    assert not chatsync.live(con)
    monkeypatch.setattr(bot, "_sync_live", False)
    assert "chat_member" not in json.loads(bot._wanted(cfg))
    monkeypatch.setattr(bot, "_sync_live", True)
    assert "chat_member" in json.loads(bot._wanted(cfg))


def test_consent_version_and_policy_page(env):
    c, cfg = env
    on = TestClient(server.create(dataclasses.replace(cfg, chat_sync=True)))
    assert logic.policy(dataclasses.replace(cfg, chat_sync=True)).endswith(logic.account.CONSENT_CHS)
    assert logic.account.CONSENT_CHS not in logic.policy(cfg)
    assert "<!--chs" not in on.get("/privacy?lang=en").text and "CHAT_SYNC" not in c.get("/privacy?lang=ru").text
    chatsync.POLICY = ""  # app.create set the module global: not into the next test


def test_account_deletion(club):
    c, cfg, con, org = club
    assert ("chat_sync_todo", "user_id") in logic._DEL_GONE
    chatsync.member_update(con, upd(MAIN, 1, "left", "member"))
    chatsync.member_update(con, upd(DEPT, 1, "left", "member", date=logic.core.now() + 2))
    con.execute("INSERT INTO chat_sync_todo (chat_id, user_id, op) VALUES (?, ?, 'drop')", (MAIN, uid(con, 1)))
    gone = uid(con, 1)
    delete_now(c, cfg, tma(1))
    for t in ("chat_sync_todo", "member_tags", "org_members"):
        assert not con.execute(f"SELECT 1 FROM {t} WHERE user_id = ?", (gone,)).fetchone()
