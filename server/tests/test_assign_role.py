"""One club role to many people at once (PUT /orgs/{oid}/roles/{rid}/people): the per-person rank rule, the skipped
count, untick removes, the fixed ranks refused, audit per change."""
from __future__ import annotations

from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_team_link import _club


def test_assign_role_many(env):
    c, cfg = env
    pres, vice, a, b, h = login(c, 20, "pres"), login(c, 21, "vice"), login(c, 22, "aaa"), login(c, 23, "bbb"), login(c, 24, "hhh")
    con = _club(cfg, pres["id"], **{f"u{vice['id']}": "vice", f"u{a['id']}": "member", f"u{b['id']}": "member", f"u{h['id']}": "member"})
    P, V = tma(20), tma(21)
    roles = c.post("/api/orgs/1/roles", headers=P, json={"name": "SMM", "color": "#112233", "rights": []}).json()["roles"]
    smm = next(r["id"] for r in roles if r["name"] == "SMM")
    role_of = lambda u: con.execute("SELECT role, role_id FROM org_members WHERE org_id = 1 AND user_id = ?", (u["id"],)).fetchone()
    log_n = lambda: con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'role_change'").fetchone()[0]

    # a Vice ticks two members and the President: the President is above them, skipped
    n0 = log_n()
    r = c.put(f"/api/orgs/1/roles/{smm}/people", headers=V, json={"users": [a["id"], b["id"], pres["id"]]})
    assert r.status_code == 200 and r.json()["skipped"] == 1
    assert tuple(role_of(a)) == ("member", smm) and tuple(role_of(b)) == ("member", smm) and role_of(pres)[1] is None
    assert log_n() == n0 + 2
    assert next(x for x in r.json()["setup"]["roles"] if x["id"] == smm)["count"] == 2
    # unticking b takes it off (the level stays), ticking h gives it; a, already holding it, is not logged again
    r = c.put(f"/api/orgs/1/roles/{smm}/people", headers=V, json={"users": [a["id"], h["id"]]})
    assert r.json()["skipped"] == 0 and tuple(role_of(b)) == ("member", None) and role_of(h)[1] == smm
    assert log_n() == n0 + 4
    # a member can't; the official Vice role isn't handed out this way; a role of another level than mine below me only
    assert c.put(f"/api/orgs/1/roles/{smm}/people", headers=tma(22), json={"users": []}).status_code == 403
    fixed = con.execute("INSERT INTO org_roles (org_id, name, color, level, rights, fixed, created_at) VALUES (1, 'Head', '#112233', 'head', '', 1, 0)").lastrowid
    assert c.put(f"/api/orgs/1/roles/{fixed}/people", headers=P, json={"users": [a["id"]]}).status_code == 403
    assert c.put(f"/api/orgs/1/roles/{smm}/people", headers=P, json={"users": "x"}).status_code == 400
    assert c.put("/api/orgs/1/roles/9999/people", headers=P, json={"users": []}).status_code == 404


def test_assign_role_no_own_rights_raised(env):
    """Astra: never myself (ticked or not, my role stays); a role with a right I don't have isn't mine to hand out."""
    c, cfg = env
    pres, vice, a = login(c, 20, "pres"), login(c, 21, "vice"), login(c, 22, "aaa")
    con = _club(cfg, pres["id"], **{f"u{vice['id']}": "vice", f"u{a['id']}": "member"})
    P, V = tma(20), tma(21)
    new = lambda name, rights: next(r["id"] for r in c.post("/api/orgs/1/roles", headers=P, json={"name": name, "color": "#112233", "rights": rights}).json()["roles"] if r["name"] == name)  # noqa: E731
    coord, lead, smm = new("Coord", ["team"]), new("Lead", ["events"]), new("SMM", [])
    assert c.patch(f"/api/orgs/1/members/{vice['id']}", headers=P, json={"roleId": coord}).status_code == 200  # a Vice without "events"
    mine = lambda: tuple(con.execute("SELECT role, role_id FROM org_members WHERE org_id = 1 AND user_id = ?", (vice["id"],)).fetchone())  # noqa: E731
    r = c.put(f"/api/orgs/1/roles/{smm}/people", headers=V, json={"users": [vice["id"], a["id"]]})
    assert r.status_code == 200 and r.json()["skipped"] == 0 and mine() == ("vice", coord)
    assert c.put(f"/api/orgs/1/roles/{lead}/people", headers=V, json={"users": [a["id"]]}).status_code == 403


def test_tag_all_any_role(env):
    """/all: anyone holding a role in the club may call it (a role of the club's own at member level too), a plain member not."""
    from kbtu import logic
    c, cfg = env
    pres, a, b = login(c, 20, "pres"), login(c, 22, "aaa"), login(c, 23, "bbb")
    con = _club(cfg, pres["id"], **{f"u{a['id']}": "member", f"u{b['id']}": "member"})
    roles = c.post("/api/orgs/1/roles", headers=tma(20), json={"name": "Vice Head", "color": "#112233", "rights": []}).json()["roles"]
    rid = next(r["id"] for r in roles if r["name"] == "Vice Head")
    c.put(f"/api/orgs/1/roles/{rid}/people", headers=tma(20), json={"users": [a["id"]]})
    con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, created_at) VALUES (-100, 1, 'main', 0)")
    con.commit()
    assert sorted(logic.chatlist.tag_all(con, -100, 22)) == [20, 23]
    assert logic.chatlist.tag_all(con, -100, 23) is None
    assert sorted(logic.chatlist.tag_all(con, -100, 23, admin=True)) == [20, 22]   # the group's Telegram admin
    assert logic.chatlist.tag_all(con, -200, 23, admin=True) == []   # a chat no club holds
