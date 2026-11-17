"""KBTU Awards on a club's card: the admin CLI adds and removes a nomination, the org JSON shows it newest first,
Admin's club page does the same, deleting the org takes its rows."""
from __future__ import annotations

import pytest

from kbtu import admin, config, db, logic
from test_core import env, login, tma  # noqa: F401  (env is a fixture)


def test_org_awards(env, monkeypatch, capsys):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    login(c, 30, "fan")
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Crystal", "CR", "crown_3d", True)

    def run(*args: str) -> str:
        capsys.readouterr()
        admin.main(list(args))
        return capsys.readouterr().out.strip()

    card = lambda: c.get(f"/api/orgs/{org}", headers=tma(30)).json()["awards"]  # noqa: E731
    assert card() == []
    assert "added" in run("org-award", str(org), "2025", "The Best Sport Event")
    assert "added" in run("org-award", "Crystal", "2026", " The Best Organization of the Year ")
    assert "already has" in run("org-award", str(org), "2026", "The Best Organization of the Year")  # a twin: a no-op
    assert card() == [{"year": 2026, "title": "The Best Organization of the Year"}, {"year": 2025, "title": "The Best Sport Event"}]
    assert next(o for o in c.get("/api/orgs", headers=tma(30)).json() if o["id"] == org)["awards"] == card()
    with pytest.raises(SystemExit):
        run("org-award", "Nobody", "2026", "X")
    with pytest.raises(SystemExit):
        run("org-award", str(org), "2026", "x" * 81)
    assert "removed" in run("org-award-del", str(org), "2025", "The Best Sport Event")
    assert card() == [{"year": 2026, "title": "The Best Organization of the Year"}]
    # Admin's club page: the admin only
    login(c, 60, "boss")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 60")
    con.commit()
    body = {"year": 2024, "title": "The Audience Choice Award", "on": True}
    assert c.put(f"/api/admin/orgs/{org}/award", headers=tma(30), json=body).status_code == 403
    assert c.put(f"/api/admin/orgs/{org}/award", headers=tma(60), json=body).json()["awards"][-1] == {"year": 2024, "title": "The Audience Choice Award"}
    assert c.put(f"/api/admin/orgs/{org}/award", headers=tma(60), json={**body, "on": False}).json()["awards"] == card()
    assert c.put(f"/api/admin/orgs/{org}/award", headers=tma(60), json={**body, "year": "x"}).status_code == 400
    # the org gone: its rows go with it
    with db.tx(con):
        con.execute("DELETE FROM orgs WHERE id = ?", (org,))
    assert con.execute("SELECT COUNT(*) FROM org_awards").fetchone()[0] == 0
