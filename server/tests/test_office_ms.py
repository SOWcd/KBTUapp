"""KBTU staff without a student ID (DMP) sign in with Microsoft alone, only on the creator's explicit word (kbtu.admin
staff-ok): then the policy, no student ID. Office membership, roles and audit lines never count (Codex review, Nov 17)."""
from __future__ import annotations

import base64
import json

import httpx

from kbtu import admin, config, db, logic, msauth
from kbtu.logic import Viewer
from test_core import env, tma  # noqa: F401  (env is a fixture)


def test_staff_ok_sign_in(env, monkeypatch, capsys):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Youth office", "YO", "crown_3d", True)
    con.execute("UPDATE orgs SET kind = 'office', can_oversee = 1 WHERE id = ?", (org,))
    con.commit()
    part = base64.urlsafe_b64encode(json.dumps({"tid": msauth.KBTU, "appid": msauth.CLIENT}).encode()).decode().rstrip("=")
    graph = {}

    async def get(self, url, **kw):
        return httpx.Response(200, json=graph)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    uid = lambda tg: c.get("/api/me", headers=tma(tg)).json()["id"]  # noqa: E731
    row = lambda u: con.execute("SELECT student_id, first_name, last_name, consent_version, consent_at, manual FROM students WHERE user_id = ?", (u,)).fetchone()  # noqa: E731
    granted = lambda u: con.execute("SELECT 1 FROM staff_ok WHERE user_id = ?", (u,)).fetchone() is not None  # noqa: E731

    def sign_in(tg, oid, company=None):
        graph.clear()
        graph.update({"id": oid, "givenName": "Aru", "surname": "Staffova", "userPrincipalName": f"{oid}@kbtu.kz", **({"companyName": company} if company else {})})
        held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(tg)), "token": f"h.{part}.s"}).json()
        assert c.post("/api/ms/claim", headers=tma(tg), json=held).json() == {"ok": True}
        return c.get("/api/me", headers=tma(tg)).json()

    def staff_form(tg, consent=logic.CONSENT):
        return c.post("/api/kbtu/manual", headers=tma(tg), json={"consentVersion": consent, "firstName": "", "lastName": "", "studentId": "", "course": 0})

    # finding 1: an app admin's role in the office gives nothing: the ordinary form, the ID asked
    a = uid(80)
    logic.set_role(con, None, a, org, "head", "app")
    me = sign_in(80, "oid-a")
    assert me["msPending"] and "msOnly" not in me and row(a) is None
    assert staff_form(80).status_code == 400                                   # no ID: refused as ever
    # finding 2: given by hand, removed, back by a member link (no role line): nothing either
    b = uid(81)
    logic.set_role(con, None, b, org, "member", "cli")
    logic.set_role(con, None, b, org, "none", "cli")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, b))
    con.commit()
    assert "msOnly" not in sign_in(81, "oid-b") and row(b) is None

    # the creator's word: Microsoft, then the policy (its version and time saved), no ID; no office needed
    d = uid(82)
    admin.main(["staff-ok", "82"])
    assert granted(d) and c.get("/api/me", headers=tma(82)).json()["msOnly"] is True   # the welcome's sign-in shows
    me = sign_in(82, "oid-d")
    assert me["msOnly"] is True and me["msPending"] and row(d) is None          # nothing made before the policy
    assert staff_form(82, "").status_code == 400                                # finding 3: no acceptance, no row
    assert staff_form(82, "old-version").status_code == 400
    r = staff_form(82)
    assert r.status_code == 200 and r.json()["student"]["ms"]
    s = row(d)
    assert (s["student_id"], s["first_name"], s["last_name"], s["consent_version"], s["manual"]) == (f"staff{d}", "Aru", "Staffova", logic.CONSENT, 0)
    assert s["consent_at"] > 0
    assert con.execute("SELECT card_no FROM users WHERE id = ?", (d,)).fetchone()[0] is None  # staff take no card number
    assert con.execute("SELECT 1 FROM audit_log WHERE action = 'staff_ok' AND target = ?", (f"user:{d}",)).fetchone()

    # finding 4: Microsoft calls them a student: the grant doesn't apply, the ordinary form
    e = uid(83)
    admin.main(["staff-ok", "83"])
    me = sign_in(83, "oid-e", company="Student")
    assert "msOnly" not in me and staff_form(83).status_code == 400 and row(e) is None

    # revoke: the grant and the row its sign-in made go; the next sign-in is a student's
    admin.main(["staff-ok", "revoke", "82"])
    assert not granted(d) and row(d) is None
    assert "msOnly" not in sign_in(82, "oid-d")
    # ... a row typed by the creator (`staff`, consent 'staff') stays on revoke
    f = uid(84)
    admin.main(["staff", "84", "Typed", "Staff"])
    admin.main(["staff-ok", "84"])
    admin.main(["staff-ok", "revoke", "84"])
    assert row(f)["consent_version"] == "staff"
    # a student already: refused
    g = uid(85)
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at) VALUES (?, '24B099085', 'Real', 'Student', 2, ?, 0, 0, 0)""", (g, logic.CONSENT))
    con.commit()
    try:
        admin.main(["staff-ok", "85"])
        raise AssertionError("granted to a student")
    except SystemExit:
        pass
    assert not granted(g)
    capsys.readouterr()
    admin.main(["staff-ok", "list"])
    assert "@83" in capsys.readouterr().out

    # unlink and deleting the account clear the grant
    h = uid(86)
    admin.main(["staff-ok", "86"])
    admin.main(["unlink", "86"])
    assert not granted(h)
    admin.main(["staff-ok", "86"])
    logic.delete_me(con, Viewer(h, "user", True))
    con.commit()
    assert not granted(h)
