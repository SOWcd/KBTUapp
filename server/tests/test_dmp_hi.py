"""DMP's list (kbtu.admin dmp): the creator names DMP's staff by Telegram id or username before they open the app; an
unverified one gets the office's one-time hello (me.dmpHi, remembered on the server) and staff_ok's Microsoft-only sign-in."""
from __future__ import annotations

from kbtu import admin, auth, config, db, logic
from kbtu.logic import Viewer
from test_core import BOT, env, tma  # noqa: F401  (env is a fixture)


def test_dmp_hi(env, monkeypatch, capsys):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Youth office", "YO", "crown_3d", True)
    con.execute("UPDATE orgs SET kind = 'office', slug = 'dmp' WHERE id = ?", (org,))
    con.commit()
    named = lambda tg, user: {"Authorization": "tma " + auth.sign_init_data({"id": tg, "first_name": "D", "username": user}, BOT)}  # noqa: E731
    me = lambda h: c.get("/api/me", headers=h).json()  # noqa: E731

    admin.main(["dmp", "add", "90", "@DmpOne"])
    admin.main(["dmp", "add", "90"])                                     # a second run adds nothing
    assert con.execute("SELECT COUNT(*) FROM dmp_list").fetchone()[0] == 2
    by_id, by_name, other = me(tma(90)), me(named(91, "dmpone")), me(tma(92))
    assert by_id["dmpHi"]["id"] == org and by_id["msOnly"] is True       # the hello, then Microsoft with no student ID
    assert by_name["dmpHi"]["id"] == org and by_name["msOnly"] is True   # by username, any case
    assert other["dmpHi"] is None and "msOnly" not in other              # nobody else changes

    assert c.post("/api/me/dmp-hi", headers=tma(90)).status_code == 204
    again = me(tma(90))
    assert again["dmpHi"] is None and again["msOnly"] is True            # once: the sign-in stays
    assert me(named(91, "dmpone"))["dmpHi"] is not None                  # someone else's row untouched

    # signed in already: no hello
    uid = by_name["id"]
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at) VALUES (?, ?, 'Aru', 'Staffova', 2, ?, 0, 0, 0)""", (uid, f"staff{uid}", logic.CONSENT))
    con.commit()
    assert me(named(91, "dmpone"))["dmpHi"] is None

    capsys.readouterr()
    admin.main(["dmp", "list"])
    out = capsys.readouterr().out
    assert "90: greeted" in out and "@DmpOne: signed in" in out

    admin.main(["dmp", "del", "90"])
    assert "msOnly" not in me(tma(90))
    logic.delete_me(con, Viewer(uid, "user", True))                      # deleting the account takes it off the list
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM dmp_list").fetchone()[0] == 0
