"""Club presidents' asks (Nov 6): always-open recruitment carries the club's own questions (as a round's), their answers
reach the join inbox; a President deletes a club made by mistake only while it is empty (logic/clubs.py)."""
from __future__ import annotations

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

PRES, ALI, BOB = 70, 71, 72
QS = [{"kind": "long", "text": "Why us?", "required": True}, {"kind": "one", "text": "Hours", "options": ["1-4", "5+"], "required": False}]


def _club(env):
    c, cfg = env
    ids = {tg: login(c, tg, f"p{tg}")["id"] for tg in (PRES, ALI, BOB)}
    con = db.connect(cfg.db_path)
    oid = logic.create_org(con, None, "Chess Club", "CH", "crown_3d", False)
    logic.set_role(con, None, ids[PRES], oid, "president", "test")
    return c, con, ids, oid


def test_join_questions(env):
    c, con, ids, oid = _club(env)
    P, A = tma(PRES), tma(ALI)
    assert c.patch(f"/api/orgs/{oid}", headers=A, json={"joinQuestions": QS}).status_code == 403
    assert c.patch(f"/api/orgs/{oid}", headers=P, json={"joinQuestions": [{"kind": "one", "text": "x", "options": ["a"]}]}).status_code == 400
    o = c.patch(f"/api/orgs/{oid}", headers=P, json={"recruiting": True, "joinQuestions": QS}).json()
    assert [(q["id"], q["text"], q["options"], q["required"]) for q in o["joinQuestions"]] == [(0, "Why us?", None, True), (1, "Hours", ["1-4", "5+"], False)]
    assert c.get(f"/api/orgs/{oid}", headers=A).json()["joinQuestions"] == o["joinQuestions"]   # students see them

    # a required one unanswered, or an option that isn't one: no
    assert c.post(f"/api/orgs/{oid}/join-requests", headers=A, json={"answers": {"1": "1-4"}}).json()["error"] == "bad_input"
    assert c.post(f"/api/orgs/{oid}/join-requests", headers=A, json={"answers": {"0": "Love chess", "1": "9"}}).json()["error"] == "bad_input"
    assert c.post(f"/api/orgs/{oid}/join-requests", headers=A, json={"answers": {"0": "  Love chess "}}).json()["myRequest"] == "pending"
    inbox = c.get(f"/api/orgs/{oid}/join-requests", headers=P).json()
    assert inbox[0]["answers"] == [{"q": "Why us?", "a": "Love chess"}]

    # the questions change: the sent answers keep the text they answered
    c.patch(f"/api/orgs/{oid}", headers=P, json={"joinQuestions": []})
    assert c.get(f"/api/orgs/{oid}/join-requests", headers=P).json()[0]["answers"] == [{"q": "Why us?", "a": "Love chess"}]
    assert c.post(f"/api/orgs/{oid}/join-requests", headers=tma(BOB)).json()["myRequest"] == "pending"   # none: one tap, as before

    # sixty days after the club's answer, the answers go
    rid = inbox[0]["id"]
    c.post(f"/api/join-requests/{rid}/reject", headers=P)
    con.execute("UPDATE join_requests SET decided_at = decided_at - 61 * 86400 WHERE id = ?", (rid,))
    from kbtu import casting
    casting.forget(con)
    assert con.execute("SELECT answers FROM join_requests WHERE id = ?", (rid,)).fetchone()[0] is None


def test_president_deletes_empty_club(env):
    c, con, ids, oid = _club(env)
    P = tma(PRES)
    assert c.delete(f"/api/orgs/{oid}", headers=tma(ALI)).status_code == 403
    # someone else in it, or an event ever published, or official: not this way
    logic.set_role(con, None, ids[ALI], oid, "member", "test")
    assert c.delete(f"/api/orgs/{oid}", headers=P).json()["message"] == "members"
    con.execute("DELETE FROM org_members WHERE user_id = ?", (ids[ALI],))
    eid = con.execute("""INSERT INTO events (org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (?, 'cancelled', 'Blitz', '305', 0, 'crown_3d', '#3B6BFF', 0, 0)""", (oid,)).lastrowid
    assert c.delete(f"/api/orgs/{oid}", headers=P).json()["message"] == "events"
    con.execute("UPDATE events SET status = 'draft' WHERE id = ?", (eid,))   # a draft never went out: fine
    con.execute("UPDATE orgs SET official = 1 WHERE id = ?", (oid,))
    assert c.delete(f"/api/orgs/{oid}", headers=P).json()["message"] == "official"
    con.execute("UPDATE orgs SET official = 0 WHERE id = ?", (oid,))

    assert c.delete(f"/api/orgs/{oid}", headers=P).json() == {"ok": True}
    # hidden as the admin hides (the admin can bring it back), the President out of it, the audit log has it
    assert con.execute("SELECT status FROM orgs WHERE id = ?", (oid,)).fetchone()[0] == "hidden"
    assert c.get("/api/me", headers=P).json()["memberships"] == []
    assert c.get(f"/api/orgs/{oid}", headers=P).status_code == 404
    assert con.execute("SELECT actor_id FROM audit_log WHERE action = 'org_delete' AND target = ?", (f"org:{oid}",)).fetchone()[0] == ids[PRES]
    assert c.delete(f"/api/orgs/{oid}", headers=P).status_code == 404
