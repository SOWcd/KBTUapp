"""An office's own people (DMP: staff, no student ID), given the role by hand, sign in with Microsoft alone: the staff
row with the directory's names, no ID asked (account.ms_apply). Anyone else, or a row already there: as before."""
from __future__ import annotations

import base64
import json

import httpx

from kbtu import db, logic, msauth
from kbtu.logic import Viewer
from test_core import env, tma  # noqa: F401  (env is a fixture)


def test_office_member_signs_in_with_microsoft_alone(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Youth office", "YO", "crown_3d", True)
    con.execute("UPDATE orgs SET kind = 'office', can_oversee = 1 WHERE id = ?", (org,))
    club = logic.create_org(con, None, "Chess", "CH", "crown_3d", True)
    con.commit()
    part = base64.urlsafe_b64encode(json.dumps({"tid": msauth.KBTU, "appid": msauth.CLIENT}).encode()).decode().rstrip("=")
    graph = {}

    async def get(self, url, **kw):
        return httpx.Response(200, json=graph)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    uid = lambda tg: c.get("/api/me", headers=tma(tg)).json()["id"]  # noqa: E731

    def sign_in(tg, oid):
        graph.update({"id": oid, "givenName": "Aru", "surname": "Staffova", "userPrincipalName": f"{oid}@kbtu.kz"})
        held = c.post("/api/ms/finish", json={"state": msauth.state_for(cfg.token_key, uid(tg)), "token": f"h.{part}.s"}).json()
        assert c.post("/api/ms/claim", headers=tma(tg), json=held).json() == {"ok": True}
        return c.get("/api/me", headers=tma(tg)).json()

    row = lambda u: con.execute("SELECT student_id, first_name, last_name, consent_version, manual, ms_oid FROM students WHERE user_id = ?", (u,)).fetchone()  # noqa: E731

    # given by the creator's CLI (or Admin's "app"): staff at once, the directory's names, the office's rights working
    a = uid(80)
    logic.set_role(con, None, a, org, "head", "cli")
    me = sign_in(80, "oid-a")
    assert me["msPending"] is None and me["student"]["ms"] and me["student"]["consent"] == "staff"
    assert tuple(row(a)) == (f"staff{a}", "Aru", "Staffova", "staff", 0, "oid-a")
    assert [m["org"]["id"] for m in me["memberships"]] == [org] and me["oversee"] and me["office"] is None
    assert c.get("/api/registry/orgs", headers=tma(80)).status_code == 200

    # a membership not given by hand (a leftover of `kbtu.admin unlink`: a link joined while a student): the form, as before
    b = uid(81)
    logic.set_role(con, None, b, org, "member", "link")
    assert sign_in(81, "oid-b")["msPending"] is not None and row(b) is None
    # an office given by hand once, then its latest line not (a roster row): no
    d = uid(84)
    logic.set_role(con, None, d, org, "member", "app")
    logic.set_role(con, None, d, org, "vice", "roster")
    assert sign_in(84, "oid-d")["msPending"] is not None and row(d) is None
    # a club's role given by hand is no office: the form
    e = uid(85)
    logic.set_role(con, None, e, club, "president", "cli")
    assert sign_in(85, "oid-e")["msPending"] is not None and row(e) is None
    # nobody's member: unchanged
    assert sign_in(82, "oid-f")["msPending"] is not None and row(uid(82)) is None
    # a hidden office: no
    g = uid(86)
    logic.set_role(con, None, g, org, "member", "cli")
    con.execute("UPDATE orgs SET status = 'hidden' WHERE id = ?", (org,))
    con.commit()
    assert sign_in(86, "oid-g")["msPending"] is not None and row(g) is None
    con.execute("UPDATE orgs SET status = 'active' WHERE id = ?", (org,))
    con.commit()

    # a row already there (typed in before Microsoft, manual = 1): confirmed as ever, never turned into staff
    h = uid(83)
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B099083', 'Typed', 'Person', 2, 'v2', 0, 0, 0, 1)""", (h,))
    con.commit()
    logic.set_role(con, None, h, org, "member", "cli")
    sign_in(83, "oid-h")
    assert tuple(row(h)) == ("24B099083", "Aru", "Staffova", "v2", 0, "oid-h")  # ms_link's usual: Microsoft's names over typed ones

    # deleting the account takes the staff row and the membership with it
    logic.delete_me(con, Viewer(a, "user", True))
    con.commit()
    assert row(a) is None and con.execute("SELECT 1 FROM org_members WHERE user_id = ?", (a,)).fetchone() is None
