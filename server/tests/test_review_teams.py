"""Adversarial review of club membership (logic/teams.py, roster.py): each test is a way in, or a state, that the
rules should never allow."""
from __future__ import annotations

from kbtu import auth, db, logic, roster
from test_core import BOT, env, login, tma  # noqa: F401  (env: the fixture)
from test_team_link import _club


def _tg(uid: int, username: str) -> dict:
    return {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": "X", "username": username}, BOT)}


def _row(**k) -> dict:
    return {"sheet": "S", "position": None, "title": None, "role": "member", "dept": None, "full_name": "Someone Else", "school": None,
            "year": None, "course": None, "city": None, "phone": None, "tg": None, "email": None, **k}


def _member(con, uid: int) -> str | None:
    r = con.execute("SELECT role FROM org_members WHERE org_id = 1 AND user_id = ?", (uid,)).fetchone()
    return r[0] if r else None


def test_roster_claim_ignores_club_ban(env):
    """A student the club banned claims a roster row ("Yes, it's me") and is back in the club."""
    c, cfg = env
    pres, zed = login(c, 80, "pres"), login(c, 81, "zed")
    c.get("/api/me", headers=_tg(81, "zed_t"))
    con = _club(cfg, pres["id"])
    con.execute("INSERT INTO org_bans (org_id, user_id, by_id, created_at) VALUES (1, ?, ?, 0)", (zed["id"], pres["id"]))
    roster.load(con, [_row(tg="zed_t")], {"S": "it"})
    ask = c.get("/api/me", headers=_tg(81, "zed_t")).json()["roster"]["ask"]
    c.post(f"/api/roster/{ask[0]['id']}/claim", headers=_tg(81, "zed_t"))
    assert _member(con, zed["id"]) is None, "a banned student joined the club by a roster claim"


def test_roster_match_ignores_club_ban(env):
    """A banned student whose name and username match a newly loaded sheet row joins the club at once."""
    c, cfg = env
    pres, ali = login(c, 60, "pres"), login(c, 61, "ali")
    c.get("/api/me", headers=_tg(61, "ali_u"))
    con = _club(cfg, pres["id"])
    con.execute("INSERT INTO org_bans (org_id, user_id, by_id, created_at) VALUES (1, ?, ?, 0)", (ali["id"], pres["id"]))
    roster.load(con, [_row(full_name="Ali Testov", tg="ali_u", position="Head of SMM", title="Head of SMM", role="head")], {"S": "it"})
    assert _member(con, ali["id"]) is None, "a banned student joined the club (as a Head) by the roster load"


def test_roster_confirm_after_ban(env):
    """An officer's row claimed (in as a member), then removed and banned; the waiting claim, confirmed, brings them
    back as the row's officer."""
    c, cfg = env
    pres, zed = login(c, 80, "pres"), login(c, 81, "zed")
    c.get("/api/me", headers=_tg(81, "zed_t"))
    con = _club(cfg, pres["id"])
    roster.load(con, [_row(tg="zed_t", position="Head of SMM", title="Head of SMM", role="head")], {"S": "it"})
    ask = c.get("/api/me", headers=_tg(81, "zed_t")).json()["roster"]["ask"]
    assert c.post(f"/api/roster/{ask[0]['id']}/claim", headers=_tg(81, "zed_t")).status_code == 204
    assert _member(con, zed["id"]) == "member"
    assert c.post(f"/api/orgs/1/members/{zed['id']}/remove", headers=tma(80), json={"ban": True}).json() == {"done": True}
    req = c.get("/api/roster/requests", headers=tma(80)).json()
    c.post(f"/api/roster/requests/{req[0]['id']}", headers=tma(80), json={"ok": True})
    assert _member(con, zed["id"]) is None, "a banned student came back (as a Head) by a claim confirmed later"


def test_roster_title_rights_above_role(env):
    """A sheet row "member, HR" where the club has its own Vice-level role named HR: the student joins as a Member
    holding that role's rights (team), a Member with the Vice's powers (role and role level out of step)."""
    c, cfg = env
    pres, ali = login(c, 60, "pres"), login(c, 61, "ali")
    c.get("/api/me", headers=_tg(61, "ali_u"))
    con = _club(cfg, pres["id"])
    assert c.post("/api/orgs/1/roles", headers=tma(60), json={"name": "HR", "color": "#112233", "rights": ["team"]}).status_code == 200
    roster.load(con, [_row(full_name="Ali Testov", tg="ali_u", position="HR", title="HR")], {"S": "it"})
    assert _member(con, ali["id"]) == "member"
    assert "team" not in logic.rights_of(con, ali["id"], 1), "a Member holds the Vice-level right 'team'"
    assert c.post("/api/orgs/1/team-link", headers=tma(61)).status_code == 403


def test_delete_role_grants_level_rights(env):
    """A Vice who lacks 'people' deletes a Head-level role that carried 'events' only: its holder now has every Head
    right ('people', 'posts', 'casting'), rights no one gave them and the Vice doesn't have."""
    c, cfg = env
    pres, vice, mem = login(c, 20, "pres"), login(c, 21, "vice"), login(c, 22, "mem")
    con = _club(cfg, pres["id"], **{f"u{vice['id']}": "vice", f"u{mem['id']}": "member"})
    P = tma(20)
    roles = c.post("/api/orgs/1/roles", headers=P, json={"name": "Events", "color": "#112233", "rights": ["events"]}).json()["roles"]
    ev = next(r["id"] for r in roles if r["name"] == "Events")
    roles = c.post("/api/orgs/1/roles", headers=P, json={"name": "Gate", "color": "#112233", "rights": ["team"]}).json()["roles"]
    gate = next(r["id"] for r in roles if r["name"] == "Gate")
    assert c.patch(f"/api/orgs/1/members/{mem['id']}", headers=P, json={"roleId": ev}).status_code == 200
    assert c.patch(f"/api/orgs/1/members/{vice['id']}", headers=P, json={"roleId": gate}).status_code == 200
    assert "people" not in logic.rights_of(con, vice["id"], 1) and logic.rights_of(con, mem["id"], 1) == {"door", "events"}
    c.delete(f"/api/orgs/1/roles/{ev}", headers=tma(21))
    assert logic.rights_of(con, mem["id"], 1) <= {"door", "events"}, "deleting a role's name gave its holder more rights"


def test_roster_claim_race(env, monkeypatch):
    """Two students (one by the row's username, one by its e-mail) claim the same officer's row at once: the second
    overwrites the first's claim, and the first stays in the club for good: a 'no' only takes the later one out."""
    c, cfg = env
    pres, zed, bek = login(c, 80, "pres"), login(c, 81, "zed"), login(c, 82, "bek")
    c.get("/api/me", headers=_tg(81, "zed_t"))
    con = _club(cfg, pres["id"])
    con.execute("UPDATE students SET email = 'bek.t@kbtu.kz' WHERE user_id = ?", (bek["id"],))
    roster.load(con, [_row(tg="zed_t", email="bek.t@kbtu.kz", position="Head of SMM", title="Head of SMM", role="head")], {"S": "it"})
    rid = con.execute("SELECT id FROM roster_pending").fetchone()[0]
    real, raced = roster.asks, []

    def racing(con_, uid):
        r = real(con_, uid)
        if uid == zed["id"] and not raced:  # bek's claim runs to its end between zed's read and zed's write
            raced.append(1)
            other = db.connect(cfg.db_path)
            roster.claim(other, bek["id"], rid)
            other.close()
        return r
    monkeypatch.setattr(roster, "asks", racing)
    try:
        roster.claim(con, zed["id"], rid)
    except logic.ApiError:
        pass  # refused: the right answer
    monkeypatch.setattr(roster, "asks", real)
    req = c.get("/api/roster/requests", headers=tma(80)).json()
    assert len(req) == 1
    assert c.post(f"/api/roster/requests/{req[0]['id']}", headers=tma(80), json={"ok": False}).status_code == 204
    left = {u["id"]: _member(con, u["id"]) for u in (zed, bek)}
    assert left == {zed["id"]: None, bek["id"]: None}, f"still in the club after the claim was declined: {left}"
