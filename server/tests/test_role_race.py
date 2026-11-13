"""A demotion landing while the demoted admin's own request refreshes his row is never written back."""
from __future__ import annotations

from kbtu import app as appmod, db
from test_core import env, login  # noqa: F401  (env: the fixture)


def test_demotion_not_rolled_back(env, monkeypatch):
    c, cfg = env
    login(c, 40, "adm")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', seen_at = 0 WHERE tg_id = 40")  # seen long ago: the request writes the row
    maybe = db.maybe

    def demoted_meanwhile(con_, fn, *a, **kw):  # the creator's demotion commits between the request's read and its write
        con_.execute("UPDATE users SET role = 'user' WHERE tg_id = 40")
        return maybe(con_, fn, *a, **kw)
    monkeypatch.setattr(appmod.db, "maybe", demoted_meanwhile)
    v = appmod._upsert(con, {"id": 40, "first_name": "adm"}, frozenset())
    assert con.execute("SELECT role FROM users WHERE tg_id = 40").fetchone()[0] == "user" and v.role == "user"
    monkeypatch.setattr(appmod.db, "maybe", maybe)
    con.execute("UPDATE users SET seen_at = 0 WHERE tg_id = 40")
    assert appmod._upsert(con, {"id": 40, "first_name": "adm"}, frozenset({40})).role == "admin"   # ADMIN_TG_IDS still win
