import pytest

from kbtu import db, logic
from test_core import delete_now, env, login, tma  # noqa: F401


def test_erasure_revokes_staff_grants(env):
    c, cfg = env
    uid = login(c, 80, "staff")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
    delete_now(c, cfg, tma(80))
    assert c.get("/api/me", headers=tma(80)).json()["role"] == "user"
    assert login(c, 80, "staff")["role"] == "user"


def test_registry_export_requires_verified_account(env):
    c, cfg = env
    uid = c.get("/api/me", headers=tma(81)).json()["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
    with pytest.raises(logic.ApiError):
        logic.registry_export(con, logic.Viewer(uid, "admin", False))
    assert not con.execute("SELECT 1 FROM audit_log WHERE action = 'registry_export'").fetchone()


def test_startup_drops_admins_no_longer_configured(env):
    import dataclasses
    from kbtu import app

    c, cfg = env
    con = db.connect(cfg.db_path)
    uids = [login(c, tg, name)["id"] for tg, name in ((80, "removed"), (81, "appointed"), (82, "bootstrap"), (83, "owner"))]
    con.execute("UPDATE users SET role = 'admin'")
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (uids[3],))
    # An erasure anonymized someone's appointment: it grants nobody. A by-hand appointment keeps its target.
    logic.log_action(con, None, "staff_role", "user", '{"to":"admin"}')
    logic.log_action(con, None, "staff_role", f"user:{uids[1]}", '{"to":"admin"}')
    app.create(dataclasses.replace(cfg, admins=frozenset({82})))
    assert [con.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()[0] for uid in uids] == ["user", "admin", "admin", "admin"]
    assert con.execute("SELECT json_extract(data, '$.to') FROM audit_log WHERE action = 'staff_role' AND target = ?",
                       (f"user:{uids[0]}",)).fetchone()[0] == "user"
