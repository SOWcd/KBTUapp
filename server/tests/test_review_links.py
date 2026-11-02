"""Review 2: a club's member links die with their maker's right to make them."""
from __future__ import annotations

from test_core import env, login, tma  # noqa: F401  (env: the fixture)
from test_team_link import _club


def test_links_of_a_removed_vice(env):
    """A Vice who made the team link and a one-time link, then removed and banned: neither lets anyone in, nor the Vice
    back. ponytail: no revocation on removal, the maker's right is checked when a link is opened."""
    c, cfg = env
    pres, vice = login(c, 20, "pres"), login(c, 21, "vice")
    login(c, 30, "aaa"), login(c, 31, "bbb")
    con = _club(cfg, pres["id"], **{f"u{vice['id']}": "vice"})
    V = tma(21, "Vice")
    team = c.post("/api/orgs/1/team-link", headers=V).json()["token"]
    once = c.post("/api/orgs/1/invites", headers=V).json()["token"]
    assert c.delete(f"/api/orgs/1/members/{vice['id']}", headers=tma(20, "Pres")).status_code == 204  # out, not banned
    assert c.post(f"/api/invites/{once}", headers=V).status_code == 404     # not back by their own leftover link
    assert c.post(f"/api/invites/{team}", headers=tma(30)).status_code == 404
    assert c.post(f"/api/invites/{once}", headers=tma(31)).status_code == 404
    assert con.execute("SELECT COUNT(*) FROM org_members WHERE org_id = 1").fetchone()[0] == 1


def test_president_link_of_a_demoted_admin(env):
    """An admin's President link, the admin then demoted: it makes nobody the President."""
    from kbtu import db, logic
    c, cfg = env
    boss, ali = login(c, 60, "boss"), login(c, 61, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'chess', 'club', 'Chess Club', 'CH', 'trophy_3d', 0)")
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    token = logic.president_link(con, logic.Viewer(id=boss["id"], role="admin", student=True), 1)["token"]
    con.execute("UPDATE users SET role = 'user' WHERE id = ?", (boss["id"],))
    assert c.post(f"/api/invites/{token}", headers=tma(61, "Ali")).status_code == 404
    assert con.execute("SELECT COUNT(*) FROM org_members WHERE user_id = ?", (ali["id"],)).fetchone()[0] == 0
