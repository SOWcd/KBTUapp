"""DMP's list (kbtu.admin dmp): the creator names DMP's staff by Telegram id or username before they open the app; an
unverified one gets the office's one-time hello (me.dmpHi, remembered on the server) and staff_ok's Microsoft-only sign-in.
Only an id grants it: a username binds to the Telegram whose own signed data first shows it (account.dmp_bind)."""
from __future__ import annotations

import pytest

from kbtu import admin, auth, config, db, logic
from test_core import BOT, delete_now, env, login, tma  # noqa: F401  (env is a fixture)


def _setup(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    org = logic.create_org(con, None, "Youth office", "YO", "crown_3d", True)
    con.execute("UPDATE orgs SET kind = 'office', slug = 'dmp' WHERE id = ?", (org,))
    con.commit()
    return c, cfg, con, org


def named(tg: int, user: str) -> dict:
    return {"Authorization": "tma " + auth.sign_init_data({"id": tg, "first_name": "D", "username": user}, BOT)}


def staff_signed(con, uid: int) -> None:
    """The row a staff_ok / DMP sign-in makes (the policy's version, not 'staff')."""
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at) VALUES (?, ?, 'Aru', 'Staffova', 2, ?, 0, 0, 0)""", (uid, f"staff{uid}", logic.CONSENT))
    con.commit()


def test_dmp_hi(env, monkeypatch, capsys):
    c, cfg, con, org = _setup(env, monkeypatch)
    me = lambda h: c.get("/api/me", headers=h).json()  # noqa: E731
    count = lambda: con.execute("SELECT COUNT(*) FROM dmp_list").fetchone()[0]  # noqa: E731

    admin.main(["dmp", "add", "90", "@DmpOne"])
    admin.main(["dmp", "add", "90"])                                     # a second run adds nothing
    assert count() == 2
    for bad in (["https://t.me/x"], ["-5"], ["99999999999999999999"], ["90", "@a b"]):  # a malformed batch writes nothing
        with pytest.raises(SystemExit):
            admin.main(["dmp", "add", *bad])
    assert count() == 2

    by_id, by_name, other = me(tma(90)), me(named(91, "dmpone")), me(tma(92))
    assert by_id["dmpHi"]["id"] == org and by_id["msOnly"] is True       # the hello, then Microsoft with no student ID
    assert by_name["dmpHi"]["id"] == org and by_name["msOnly"] is True   # by username, any case: bound to 91 now
    assert other["dmpHi"] is None and "msOnly" not in other              # nobody else changes
    taker = me(named(93, "DmpOne"))                                      # the handle passed on: its next holder gets nothing
    assert taker["dmpHi"] is None and "msOnly" not in taker
    assert me(named(91, "renamed"))["msOnly"] is True                    # the bound id keeps it through a rename

    assert c.post("/api/me/dmp-hi", headers=tma(90)).status_code == 204
    again = me(tma(90))
    assert again["dmpHi"] is None and again["msOnly"] is True            # once: the sign-in stays
    assert me(named(91, "renamed"))["dmpHi"] is not None                 # someone else's row untouched

    # an office member: greeted as DMP once, the office's own hello doesn't come again on another phone
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, by_id["id"]))
    con.commit()
    assert me(tma(90))["office"] is None

    # signed in: no hello; `dmp list` reads Microsoft's confirmed row only
    uid = by_name["id"]
    staff_signed(con, uid)
    assert me(named(91, "renamed"))["dmpHi"] is None
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B0001', 'T', 'M', 2, ?, 0, 0, 0, 1)""", (by_id["id"], logic.CONSENT))  # typed in, Microsoft not yet
    con.commit()
    capsys.readouterr()
    admin.main(["dmp", "list"])
    out = capsys.readouterr().out
    assert "90 (Test): greeted" in out and "@DmpOne = 91 (D): signed in" in out

    # taken off the list after the sign-in: the sign-in it let in goes too
    admin.main(["dmp", "del", "@dmpone"])
    assert not con.execute("SELECT 1 FROM students WHERE user_id = ?", (uid,)).fetchone()
    assert "msOnly" not in me(named(91, "renamed"))
    assert count() == 1


def test_dmp_one_person_and_revoke(env, monkeypatch):
    c, cfg, con, org = _setup(env, monkeypatch)
    count = lambda: con.execute("SELECT COUNT(*) FROM dmp_list").fetchone()[0]  # noqa: E731

    admin.main(["dmp", "add", "94", "@Same"])                             # the same person by id and by name
    u = c.get("/api/me", headers=named(94, "same")).json()
    assert count() == 1                                                   # one row once Telegram shows they're one
    admin.main(["dmp", "del", "94"])
    assert count() == 0                                                   # one removal suffices

    admin.main(["dmp", "add", "94"])
    staff_signed(con, u["id"])
    admin.main(["staff-ok", "revoke", "94"])                              # full revocation: off the list, its sign-in undone
    assert count() == 0 and not con.execute("SELECT 1 FROM students WHERE user_id = ?", (u["id"],)).fetchone()
    admin.main(["dmp", "add", "94"])
    staff_signed(con, u["id"])
    admin.main(["unlink", "94", "--yes"])                                          # unlink: no grant left to make it again
    assert count() == 0

    # moving the account takes its grant to its new Telegram
    admin.main(["dmp", "add", "94"])
    c.get("/api/me", headers=tma(95))
    admin.main(["move", "94", "95", "--yes"])
    assert [r[0] for r in con.execute("SELECT tg_id FROM dmp_list")] == [95]
    assert "msOnly" not in c.get("/api/me", headers=tma(94)).json()


def test_dmp_erased(env, monkeypatch):
    c, cfg, con, org = _setup(env, monkeypatch)
    admin.main(["dmp", "add", "96", "@Other"])
    snapshot = cfg.db_path + ".before"
    con.execute("VACUUM INTO ?", (snapshot,))                             # a copy from before 96 ever opened the app
    login(c, 96, "dmper")
    delete_now(c, cfg, tma(96))
    assert [r[0] for r in con.execute("SELECT tg_username FROM dmp_list")] == ["Other"]  # someone else's invitation stays

    restored = db.connect(snapshot)
    logic.replay_deletions(restored)
    assert [r[0] for r in restored.execute("SELECT tg_username FROM dmp_list")] == ["Other"]  # the erased grant stays erased
    logic.replay_deletions(restored)
    assert restored.execute("SELECT COUNT(*) FROM dmp_list").fetchone()[0] == 1
