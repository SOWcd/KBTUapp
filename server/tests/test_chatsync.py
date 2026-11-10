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


_ids = iter(range(1, 10**6))


def feed(con, u, update_id=None):
    """A chat_member update as the bot's ears pass it: its own update id, each newer than the last."""
    chatsync.member_update(con, u, update_id or next(_ids) + 1000)


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
    feed(con, upd(MAIN, 1, "left", "member"))
    assert role(con, org, 1) == "member"
    line = con.execute("SELECT actor_id, data FROM audit_log WHERE action = 'role_change' AND target = ?", (f"user:{uid(con, 1)}",)).fetchone()
    assert line[0] is None and json.loads(line[1]) == {"org": org, "role": "member", "by": "sync", "sync": MAIN}
    feed(con, upd(MAIN, 2, "left", "restricted", is_member=True))  # restricted, still a member
    feed(con, upd(MAIN, 3, "left", "restricted", is_member=False))
    assert role(con, org, 2) == "member" and role(con, org, 3) is None
    feed(con, upd(MAIN, 1, "member", "administrator"))  # a change inside the chat: nothing
    assert role(con, org, 1) == "member"
    feed(con, upd(MAIN, 1, "member", "left"))
    feed(con, upd(MAIN, 2, "member", "kicked"))
    assert role(con, org, 1) is None and role(con, org, 2) is None
    gone = json.loads(con.execute("SELECT data FROM audit_log WHERE action = 'role_change' AND target = ? ORDER BY id DESC", (f"user:{uid(con, 1)}",)).fetchone()[0])
    assert gone == {"org": org, "role": "none", "by": "sync", "sync": MAIN}
    feed(con, upd(MAIN, 1, "left", "member", date=logic.core.now() + 5))  # rejoins: back (the sync's removal holds nothing)
    assert role(con, org, 1) == "member"
    # strangers, bots, staff, the typed-in, those not on the policy in force: nothing, and nothing stored
    n = con.execute("SELECT COUNT(*) FROM org_members").fetchone()[0]
    feed(con, upd(MAIN, 777, "left", "member"))
    bot_upd = upd(MAIN, 4, "left", "member")
    bot_upd["new_chat_member"]["user"]["is_bot"] = True
    feed(con, bot_upd)
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (uid(con, 5),))
    con.execute("UPDATE students SET consent_version = '1' WHERE user_id = ?", (uid(con, 6),))
    feed(con, upd(MAIN, 5, "left", "member"))
    feed(con, upd(MAIN, 6, "left", "member"))
    feed(con, upd(-999, 4, "left", "member"))  # a chat nobody linked
    assert con.execute("SELECT COUNT(*) FROM org_members").fetchone()[0] == n
    assert not con.execute("SELECT 1 FROM users WHERE tg_id = 777").fetchone()


def test_president_kept(club):
    c, cfg, con, org = club
    feed(con, upd(MAIN, P, "creator", "left"))
    assert role(con, org, P) == "president"
    sweep(con, chatsync_start(con, MAIN, True, tg_api({V: "member"})))
    assert role(con, org, P) == "president" and role(con, org, V) == "vice"


def chatsync_start(con, chat, apply, call):
    assert chatsync.start(con, chat, apply)
    return call


def test_paused_when_the_bot_loses_admin(club):
    c, cfg, con, org = club
    feed(con, upd(MAIN, 1, "left", "member"))
    chatsync.bot_status(con, MAIN, "member")  # demoted
    assert con.execute("SELECT paused FROM chat_sync WHERE chat_id = ?", (MAIN,)).fetchone()[0]
    feed(con, upd(MAIN, 1, "member", "left"))
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
    feed(con, upd(DEPT, 1, "left", "member"))  # not in the club: no department
    assert not con.execute("SELECT 1 FROM member_tags WHERE user_id = ?", (uid(con, 1),)).fetchone()
    feed(con, upd(MAIN, 1, "left", "member"))
    feed(con, upd(DEPT, 1, "left", "member", date=logic.core.now() + 2))
    feed(con, upd(DEPT2, 1, "left", "member", date=logic.core.now() + 2))
    assert logic.depts_of(con, org, uid(con, 1)) == sorted([media, events])
    assert con.execute("SELECT sync FROM member_tags WHERE user_id = ? AND tag_id = ?", (uid(con, 1), media)).fetchone()[0] == 1
    feed(con, upd(DEPT2, 1, "member", "left"))
    assert logic.depts_of(con, org, uid(con, 1)) == [media]  # the other stays
    # a Head whose department came by sync manages nothing by it
    con.execute("UPDATE org_members SET role = 'head' WHERE user_id = ?", (uid(con, 1),))
    assert logic.depts_of(con, org, uid(con, 1), own=True) == []
    feed(con, upd(MAIN, 1, "member", "left"))  # out of the club: its departments go too
    assert role(con, org, 1) is None and logic.depts_of(con, org, uid(con, 1)) == []


def test_manual_removal_respected(club):
    c, cfg, con, org = club
    feed(con, upd(MAIN, 1, "left", "member"))
    assert c.post(f"/api/orgs/{org}/members/{uid(con, 1)}/remove", headers=tma(P), json={}).json() == {"done": True}
    sweep(con, chatsync_start(con, MAIN, True, tg_api({P: "creator", V: "member", 1: "member"})))  # still in the chat
    assert role(con, org, 1) is None
    removed = con.execute("SELECT MAX(at) FROM audit_log WHERE action = 'role_change'").fetchone()[0]
    feed(con, upd(MAIN, 1, "left", "member", date=removed))  # an update from before the removal
    assert role(con, org, 1) is None
    feed(con, upd(MAIN, 1, "left", "member", date=removed + 1))  # joined the chat again after it
    assert role(con, org, 1) == "member"
    # a department taken by hand: the same
    media = tag(con, "Media")
    feed(con, upd(DEPT, 1, "left", "member", date=removed + 2))
    assert c.patch(f"/api/orgs/{org}/members/{uid(con, 1)}", headers=tma(V), json={"dropDept": media}).status_code == 200
    sweep(con, chatsync_start(con, DEPT, True, tg_api({1: "member"})))
    assert logic.depts_of(con, org, uid(con, 1)) == []
    # banned: never back, whatever the chat says
    assert c.post(f"/api/orgs/{org}/members/{uid(con, 1)}/remove", headers=tma(P), json={"ban": True}).status_code == 200
    feed(con, upd(MAIN, 1, "left", "member", date=logic.core.now() + 99))
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
    feed(con, upd(MAIN, 1, "left", "member"))
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
    feed(con, upd(MAIN, 1, "left", "member"))
    feed(con, upd(DEPT, 1, "left", "member", date=logic.core.now() + 2))
    con.execute("INSERT INTO chat_sync_todo (chat_id, user_id, op) VALUES (?, ?, 'drop')", (MAIN, uid(con, 1)))
    gone = uid(con, 1)
    delete_now(c, cfg, tma(1))
    for t in ("chat_sync_todo", "member_tags", "org_members"):
        assert not con.execute(f"SELECT 1 FROM {t} WHERE user_id = ?", (gone,)).fetchone()


# ---------------------------------------------------------------- Codex's adversarial review of the first version

def test_casting_gives_no_department_powers_by_self_approval(club):
    """A Head of Media approving their own application into Events: in the club already, so Events comes only as Team
    would give it by the sender's hand; a newcomer still lands in the department."""
    from kbtu import casting
    c, cfg, con, org = club
    media, events = tag(con, "Media"), tag(con, "Events")
    head, new = uid(con, 1), uid(con, 2)
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', 0)", (org, head))
    logic.set_dept(con, None, org, head, media, True)
    rid = con.execute("INSERT INTO rounds (org_id, title, closes_at, status, created_at) VALUES (?, 'r', 0, 'closed', 0)", (org,)).lastrowid
    for u in (head, new):
        con.execute("""INSERT INTO round_apps (round_id, user_id, departments, answers, stage, taken_tag, created_at, updated_at)
            VALUES (?, ?, '[]', '{}', 'yes', ?, 0, 0)""", (rid, u, events))
    casting.send(con, logic.Viewer(head, "user", True), rid)
    assert logic.depts_of(con, org, head) == [media] and logic.depts_of(con, org, new) == [events]


def test_sync_only_department_narrows_a_heads_meetings(club):
    """A Head whose own department became sync-only (left and rejoined its chat) may call no department meeting, never the
    whole club; a Head in no department at all calls the whole club as before."""
    c, cfg, con, org = club
    media = tag(con, "Media")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', 0)", (org, uid(con, 1)))
    con.execute("INSERT INTO member_tags (tag_id, user_id, sync) VALUES (?, ?, 1)", (media, uid(con, 1)))
    meet = {"title": "Sync", "place": "305", "startsAt": logic.core.now() + 86400, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": None,
            "visibility": "members", "meeting": True}
    assert c.post(f"/api/orgs/{org}/events", headers=tma(1), json=meet).json().get("message") == "dept"
    assert c.post(f"/api/orgs/{org}/events", headers=tma(1), json={**meet, "meetingTag": media}).json().get("message") == "dept"
    setup = c.get(f"/api/orgs/{org}/team", headers=tma(1)).json()
    assert setup["myDepts"] == [] and setup["inDept"] is True
    con.execute("DELETE FROM member_tags WHERE user_id = ?", (uid(con, 1),))
    assert c.post(f"/api/orgs/{org}/events", headers=tma(1), json=meet).status_code == 200


def test_stale_lookup_dropped(club):
    """A sweep's getChatMember answered "member" while a newer leave was applied: the answer is dropped, the person asked
    again, and the newer state wins."""
    c, cfg, con, org = club
    feed(con, upd(MAIN, 1, "left", "member"))
    chatsync.start(con, MAIN, True)
    state = {P: "creator", V: "member", 1: "member"}

    async def call(method, params):
        if params["user_id"] == 1 and state[1] == "member":
            feed(con, upd(MAIN, 1, "member", "left", date=logic.core.now() + 3))  # the leave lands while we ask
            state[1] = "left"
            return {"ok": True, "result": {"status": "member"}}  # the stale answer
        return await tg_api(state)(method, params)
    sweep(con, call)
    assert role(con, org, 1) is None


def test_deleted_or_ineligible_while_asked(club):
    """Eligibility is checked again where the change is made: someone who took back consent (or was deleted, banned)
    while their lookup was in flight, or before the sweep's end, isn't touched."""
    c, cfg, con, org = club
    chatsync.start(con, MAIN, True)

    async def call(method, params):
        if params["user_id"] == 1:
            con.execute("UPDATE students SET consent_version = 'old' WHERE user_id = ?", (uid(con, 1),))
        if params["user_id"] == 2:
            con.execute("UPDATE users SET delete_at = 1 WHERE tg_id = 2")
        return await tg_api({P: "creator", V: "member", 1: "member", 2: "member", 3: "member"})(method, params)
    sweep(con, call)
    assert role(con, org, 1) is None and role(con, org, 2) is None and role(con, org, 3) == "member"
    # staged, then banned before the end: not applied
    chatsync.start(con, MAIN, True)
    asyncio.run(chatsync.step(con, tg_api({P: "creator", V: "member", 3: "member", 4: "member"}), BOT_ID, 4))  # stages 4, not ended
    assert con.execute("SELECT 1 FROM chat_sync_todo WHERE user_id = ?", (uid(con, 4),)).fetchone()
    con.execute("UPDATE users SET banned_at = 1 WHERE tg_id = 4")
    sweep(con, tg_api({P: "creator", V: "member", 3: "member"}))
    assert role(con, org, 4) is None


def test_replayed_batch_skipped(club):
    """A restart before Telegram heard the ack replays the batch: the leave and join already applied change nothing,
    and a role restored since stays; an update with a lower id but a later date (Telegram's random id after a week of
    silence) still counts."""
    c, cfg, con, org = club
    t = logic.core.now() + 5
    feed(con, upd(MAIN, 1, "left", "member", date=t - 4), 5001)
    feed(con, upd(MAIN, 1, "member", "left", date=t - 4), 5002)
    feed(con, upd(MAIN, 1, "left", "member", date=t), 5003)
    con.execute("UPDATE org_members SET role = 'head' WHERE user_id = ?", (uid(con, 1),))  # restored by hand since
    feed(con, upd(MAIN, 1, "member", "left", date=t - 4), 5002)  # the replay
    feed(con, upd(MAIN, 1, "left", "member", date=t), 5003)
    assert role(con, org, 1) == "head"
    feed(con, upd(MAIN, 1, "member", "left", date=t + 100), 17)  # newer, a reset id
    assert role(con, org, 1) is None


def test_joined_before_consent_caught_up(club):
    """In the chat before agreeing to the policy in force: the join was ignored; agreeing queues one look in the linked
    chats, which adds them (main first, then the departments)."""
    c, cfg, con, org = club
    con.execute("UPDATE students SET consent_version = 'old' WHERE user_id = ?", (uid(con, 1),))
    feed(con, upd(MAIN, 1, "left", "member"))
    assert role(con, org, 1) is None
    con.execute("UPDATE students SET consent_version = 'pol' WHERE user_id = ?", (uid(con, 1),))
    with db.tx(con):
        chatsync.check_later(con, uid(con, 1))
    while asyncio.run(chatsync.ask_step(con, tg_api({1: "member"}))):
        pass
    assert role(con, org, 1) == "member" and logic.depts_of(con, org, uid(con, 1)) == sorted([tag(con, "Media"), tag(con, "Events")])
    assert not con.execute("SELECT 1 FROM chat_sync_ask").fetchone()
    assert ("chat_sync_ask", "user_id") in logic._DEL_GONE
    assert c.post("/api/me/consent", headers=tma(2), json={"version": logic.CONSENT}).status_code == 200  # the app's route queues it
    assert con.execute("SELECT 1 FROM chat_sync_ask WHERE user_id = ?", (uid(con, 2),)).fetchone()


# ---------------------------------------------------------------- Codex's re-check

def test_sync_taking_the_last_department_keeps_the_scope_narrow(club):
    """A Head of Media leaves the Media chat: the sync takes their last department, and they still call no meeting for
    the whole club; a Head whose department a Vice+ took by hand is club-wide again, as one never in any."""
    c, cfg, con, org = club
    media = tag(con, "Media")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', 0)", (org, uid(con, 1)))
    assert c.patch(f"/api/orgs/{org}/members/{uid(con, 1)}", headers=tma(V), json={"addDept": media}).status_code == 200
    feed(con, upd(DEPT, 1, "member", "left"))
    assert logic.depts_of(con, org, uid(con, 1)) == []
    meet = {"title": "All", "place": "305", "startsAt": logic.core.now() + 86400, "emoji": "laptop_3d", "color": "#3B6BFF", "seats": None,
            "visibility": "members", "meeting": True}
    assert c.post(f"/api/orgs/{org}/events", headers=tma(1), json=meet).json().get("message") == "dept"
    assert c.get(f"/api/orgs/{org}/team", headers=tma(1)).json()["inDept"] is True
    assert c.patch(f"/api/orgs/{org}/members/{uid(con, 1)}", headers=tma(V), json={"addDept": media}).status_code == 200
    assert c.patch(f"/api/orgs/{org}/members/{uid(con, 1)}", headers=tma(V), json={"dropDept": media}).status_code == 200
    assert c.post(f"/api/orgs/{org}/events", headers=tma(1), json=meet).status_code == 200


def test_fresh_look_supersedes_a_staged_finding(club):
    """A sweep staged "drop" for a Head; a fresh look (the catch-up) finds them in the chat and changes nothing: the old
    finding goes with it, so the sweep's end keeps them. The same for a staged "add" a fresh look doesn't confirm."""
    c, cfg, con, org = club
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', 0)", (org, uid(con, 1)))
    chatsync.start(con, MAIN, True)
    asyncio.run(chatsync.step(con, tg_api({P: "creator", V: "member", 2: "member"}), BOT_ID, 4))  # P, V, 1 (drop), 2 (add)
    assert {r[0] for r in con.execute("SELECT op FROM chat_sync_todo")} == {"drop", "add"}
    with db.tx(con):
        chatsync.check_later(con, uid(con, 1))
        chatsync.check_later(con, uid(con, 2))
    while asyncio.run(chatsync.ask_step(con, tg_api({P: "creator", V: "member", 1: "member"}))):
        pass
    assert not con.execute("SELECT 1 FROM chat_sync_todo").fetchone()
    sweep(con, tg_api({P: "creator", V: "member", 1: "member"}))
    assert role(con, org, 1) == "head" and role(con, org, 2) is None
