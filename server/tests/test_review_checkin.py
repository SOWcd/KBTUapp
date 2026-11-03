"""Review of QR check-in and award links: each test here fails on the code as found."""
from __future__ import annotations

from fastapi.testclient import TestClient

from kbtu import app as server, checkin, db, logic
from test_core import _club_runs, _csv, env, login, tma  # noqa: F401  (env: the fixture)


def test_csv_survives_an_unlinked_student(env):
    """`admin unlink` deletes the students row; that person's counted mark stays (done_at set). The CSV's tier column
    then compares None <= int: the whole list for the session is a 500."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    sid = checkin.new(con, "Meeting", [], _club_runs(c, con, 9, "dana"))
    ann = login(c, 1, "ann")
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
    con.execute("DELETE FROM students WHERE user_id = ?", (ann["id"],))   # what admin.py `unlink` does
    x = TestClient(server.create(cfg), raise_server_exceptions=False)
    url = x.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]
    assert x.get(url).status_code == 200
    con.close()


def test_demoted_admins_link_stops_granting(env):
    """An admin's one-time award link outlives the admin: after the owner takes the role away, the link still hands
    out the award in that person's name (granted_by is someone who can no longer grant)."""
    c, cfg = env
    boss, adm = login(c, 60, "boss"), login(c, 61, "adm")
    login(c, 62, "bob")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (adm["id"],))
    token = logic.grant_link(con, logic.Viewer(adm["id"], "admin", True), "init26")
    assert c.post("/api/admin/staff", headers=tma(60), json={"userId": adm["id"], "role": "user"}).status_code == 200
    assert c.post(f"/api/grant-links/{token}", headers=tma(62)).json().get("error") == "closed"
    con.close()


def test_share_badge_link_bad_code_is_400(env):
    """The owner's "Link for everyone" with a non-string code: `code in BADGE_OF` on a list is a TypeError, a 500."""
    c, cfg = env
    boss = login(c, 60, "boss")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    x = TestClient(server.create(cfg), raise_server_exceptions=False)
    assert x.post("/api/share", headers=tma(60), json={"kind": "gl", "code": ["init26"], "many": True}).status_code == 400
    con.close()
