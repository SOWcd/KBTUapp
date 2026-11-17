"""An office's person is told their office in /api/me before the KBTU sign-in (the app's one team greeting)."""
from __future__ import annotations

from kbtu import db, logic
from test_core import env, tma  # noqa: F401  (env is a fixture)


def test_office_before_sign_in(env):
    c, cfg = env
    assert c.get("/api/me", headers=tma(70)).json()["office"] is None
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Youth office", "YO", "crown_3d", True)
    con.execute("UPDATE orgs SET kind = 'office' WHERE id = ?", (org,))
    con.commit()
    logic.set_role(con, None, con.execute("SELECT id FROM users WHERE tg_id = 70").fetchone()[0], org, "head", "test")
    me = c.get("/api/me", headers=tma(70)).json()
    assert me["office"]["id"] == org and me["memberships"] == []
