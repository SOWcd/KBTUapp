"""Adversarial review of club membership (logic/teams.py, roster.py): each test is a way in, or a state, that the
rules should never allow."""
from __future__ import annotations

from kbtu import auth, logic, roster
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



def test_roster_match_ignores_club_ban(env):
    """A banned student whose name and username match a newly loaded sheet row joins the club at once."""
    c, cfg = env
    pres, ali = login(c, 60, "pres"), login(c, 61, "ali")
    c.get("/api/me", headers=_tg(61, "ali_u"))
    con = _club(cfg, pres["id"])
    con.execute("INSERT INTO org_bans (org_id, user_id, by_id, created_at) VALUES (1, ?, ?, 0)", (ali["id"], pres["id"]))
    con.execute("UPDATE students SET email = 'ali@kbtu.kz' WHERE user_id = ?", (ali["id"],))
    roster.load(con, [_row(full_name="Ali Testov", email="ali@kbtu.kz", tg="ali_u", position="Head of SMM", title="Head of SMM", role="head")], {"S": "it"})
    assert _member(con, ali["id"]) is None, "a banned student joined the club (as a Head) by the roster load"



def test_roster_title_rights_above_role(env):
    """A sheet row "member, HR" where the club has its own Vice-level role named HR: the student joins as a Member
    holding that role's rights (team), a Member with the Vice's powers (role and role level out of step)."""
    c, cfg = env
    pres, ali = login(c, 60, "pres"), login(c, 61, "ali")
    c.get("/api/me", headers=_tg(61, "ali_u"))
    con = _club(cfg, pres["id"])
    assert c.post("/api/orgs/1/roles", headers=tma(60), json={"name": "HR", "color": "#112233", "rights": ["team"]}).status_code == 200
    con.execute("UPDATE students SET email = 'ali@kbtu.kz' WHERE user_id = ?", (ali["id"],))
    roster.load(con, [_row(full_name="Ali Testov", email="ali@kbtu.kz", tg="ali_u", position="HR", title="HR")], {"S": "it"})
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




def test_roster_load_from_the_gate(env, monkeypatch, capsys):
    """The prod gate passes arguments only: `roster load --gz <b64 gzip {"rows", "map"}>` loads like the two files."""
    import base64
    import gzip
    import json
    from kbtu import admin, config
    monkeypatch.setattr(config, "load", lambda: env[1])
    row = {"sheet": "S", "full_name": "Test Person", "tg": "someone_x", "email": None, "phone": None, "position": "member",
           "role": "member", "title": None, "dept": None, "school": None, "course": None, "year": None, "city": None}
    blob = base64.b64encode(gzip.compress(json.dumps({"rows": [row], "map": {"S": {"new": {"name": "Gz Club", "short": "GZ"}}}}).encode())).decode()
    admin.main(["roster", "load", "--gz", blob])
    out = capsys.readouterr().out
    assert "rows 1, new 1, clubs made 1" in out
    admin.main(["roster", "load", "--gz", blob])  # again: nothing more
    assert "new 0" in capsys.readouterr().out
def test_roster_reload_never_refills_consumed_rows(env):
    """H2: a consumed row cannot restore cleared data or assign it to a recycled handle."""
    c, cfg = env
    pres, ali = login(c, 64, "pres"), login(c, 65, "ali")
    c.get("/api/me", headers=_tg(65, "ali_f"))
    con = _club(cfg, pres["id"])
    con.execute("UPDATE students SET email = 'alif@kbtu.kz', phone = NULL WHERE user_id = ?", (ali["id"],))
    con.execute("UPDATE users SET city = 'Shymkent' WHERE id = ?", (ali["id"],))
    row = _row(full_name="Ali Testov", email="alif@kbtu.kz", tg="ali_f")
    roster.load(con, [row], {"S": "it"})
    assert _member(con, ali["id"]) == "member"
    con.execute("UPDATE users SET city = NULL, tg_username = NULL WHERE id = ?", (ali["id"],))
    new_owner = login(c, 67, "new")
    c.get("/api/me", headers=_tg(67, "ali_f"))
    roster.load(con, [{**row, "phone": "+7 701 234 56 78", "city": "Almaty"}], {"S": "it"})
    profiles = con.execute("SELECT s.phone, u.city FROM users u JOIN students s ON s.user_id = u.id WHERE u.id IN (?, ?)", (ali["id"], new_owner["id"]))
    assert [tuple(r) for r in profiles] == [(None, None), (None, None)]


def test_roster_handle_only_match_still_requires_a_claim(env):
    """An existing role does not identify the owner of a different person's roster row."""
    c, cfg = env
    pres = login(c, 66, "pres")
    c.get("/api/me", headers=_tg(66, "boss_u"))
    con = _club(cfg, pres["id"])
    roster.load(con, [_row(full_name="Someone Else", tg="boss_u", position="President")], {"S": "it"})
    assert con.execute("SELECT 1 FROM roster_pending").fetchone()
    assert roster.asks(con, pres["id"])
    assert _member(con, pres["id"]) == "president"
