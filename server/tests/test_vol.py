"""The volunteers ledger (logic/vol.py, VOLUNTEERS=<slug>): the import from the club's xlsx (dry run, apply, again, undo),
hours from check-in alone (nobody types them), who left without checking out, the door handed over by a link, the
misses' validity rule, who reads and who edits, and deleting an account. The xlsx is synthetic,
made here with the club's sheet and header names (never the real file)."""
from __future__ import annotations

import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from kbtu import app as server, checkin, db, logic, xlsx
from kbtu.logic import vol
from test_core import delete_now, login, tma  # noqa: F401
from test_core import env  # noqa: F401  (the fixture)
from test_review_checkin import _scan, _signed

MEM, HRS = "ZhZh \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0438", "\u0427\u0430\u0441\u044b 26-27"  # the club's two sheets
FIO_LAT, KURS, PHONE, TG = "\u0424\u0418\u041e \u043d\u0430 \u043b\u0430\u0442\u0438\u043d\u0438\u0446\u0435", "\u041a\u0443\u0440\u0441", \
    "\u041d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430", "\u0422\u0435\u043b\u0435\u0433\u0440\u0430\u043c\u043c \u043d\u0438\u043a"
FIO, TG2 = "\u0424\u0418\u041e", "\u0442\u0433"
P = 9  # the President


def _book(extra=()) -> bytes:
    return xlsx.write({
        MEM: [["list"], [FIO_LAT, KURS, PHONE, TG], ["Aru Test", "2", "+70000000001", "@aru_t"], ["Bek Test", "3", "", "bek_test"],
              ["Cat Test", "1", "", ""], *extra],
        HRS: [[FIO, TG2, "September deposit", "Total"], ["Aru", "@aru_t", "5", "12,5"], ["Nobody Listed", "@nobody1", "1", "2"]],
    })


def _club(c, con):
    """Zhyly Zhurek with tg 9 its President; the client sees VOLUNTEERS=zhzh."""
    login(c, P, "pres")
    org = con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('zhzh', 'club', 'ZhZh', 'Z', 'trophy_3d', 0)").lastrowid
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'president', 0)", (org, _uid(c, P)))
    return org


def _agree(c, tg):
    """The policy as this person is asked it (with the ledger's +vol1 when it concerns them)."""
    v = c.get("/api/me", headers=tma(tg)).json()["consentNow"]
    assert c.post("/api/me/consent", headers=tma(tg), json={"version": v}).status_code == 200
    return v


def _uid(c, tg):
    return c.get("/api/me", headers=tma(tg)).json()["id"]


def _member(c, con, org, tg, name, role="member"):
    login(c, tg, name)
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, 0)", (org, _uid(c, tg), role))
    return _uid(c, tg)


@pytest.fixture
def zz(env):
    c0, cfg = env
    c = TestClient(server.create(dataclasses.replace(cfg, volunteers="zhzh")))
    con = db.connect(cfg.db_path)
    org = _club(c, con)
    _agree(c, P)
    yield c, cfg, con, org
    con.close()


def test_off_without_the_switch(env):
    c, cfg = env
    login(c, 1, "ann")
    assert c.get("/api/vol", headers=tma(1)).status_code == 404 and "vol" not in c.get("/api/me", headers=tma(1)).json()


def test_import_dry_run_apply_again_undo(zz):
    c, _, con, org = zz
    p = vol.plan(_book(), "Total")
    assert con.execute("SELECT COUNT(*) FROM vol_people").fetchone()[0] == 0                 # a dry run writes nothing
    heads = dict(map(tuple, p["sheets"][MEM]["headers"]))
    assert heads[FIO_LAT] == "name" and heads[TG] == "tg" and heads[PHONE] is None and heads[KURS] is None
    assert dict(map(tuple, p["sheets"][HRS]["headers"])) == {FIO: "name", TG2: "tg", "September deposit": None, "Total": None}
    assert len(p["people"]) == 4 and p["sheets"][HRS]["matched"] == 1 and p["sheets"][HRS]["new"] == 1   # Aru by @, Nobody alone
    assert any("on no row of the members sheet" in x for x in p["problems"])
    assert not any("Aru" in x or "+7" in x for x in p["problems"])                             # row numbers, never a value
    got = vol.apply(con, org, p, "list given by the club's president on 2026-11-06, evening")
    assert got == {"batch": got["batch"], "again": False, "added": 4, "there": 0, "deleted": 0}
    aru = con.execute("SELECT * FROM vol_people WHERE tg = 'aru_t'").fetchone()
    assert aru["balance"] == 750 and aru["user_id"] is None                                   # 12,5 h; no account linked by itself
    raw = __import__("json").loads(aru["raw"])
    assert raw[MEM][PHONE] == "+70000000001" and raw[HRS]["September deposit"] == "5"        # every column, as given
    assert con.execute("SELECT source FROM vol_batches").fetchone()[0].endswith("2026-11-06, evening")
    assert vol.apply(con, org, vol.plan(_book(), "Total"), "again")["again"]                 # the same file: nothing doubles
    more = vol.plan(_book([["Dan Test", "2", "", "@dan_test"]]))
    got2 = vol.apply(con, org, more, "a later list")
    assert (got2["added"], got2["there"]) == (1, 4) and con.execute("SELECT COUNT(*) FROM vol_people").fetchone()[0] == 5
    bek = con.execute("SELECT id FROM vol_people WHERE tg = 'bek_test'").fetchone()[0]
    con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at) VALUES (?, 1, 2)", (bek,))     # used since: stays
    assert vol.undo(con, org, got["batch"]) == {"gone": 3, "kept": 1}
    assert {r[0] for r in con.execute("SELECT tg FROM vol_people")} == {"bek_test", "dan_test"}
    again = vol.apply(con, org, vol.plan(_book()), "after the undo")                         # an undone file may come again
    assert not again["again"] and again["added"] == 3


def test_import_refuses_bad_files():
    with pytest.raises(xlsx.Bad):
        vol.plan(b"not a zip")
    with pytest.raises(xlsx.Bad):
        vol.plan(b"x" * (xlsx.MAX_FILE + 1))
    big = xlsx.write({MEM: [[FIO_LAT, TG]] + [["N", "@abcd"]] * (xlsx.MAX_ROWS + 1)})
    with pytest.raises(xlsx.Bad):
        vol.plan(big)


def _meet(c, con, org, team=True, title="Teambuilding"):
    sid = checkin.new(con, title, [], org)
    if team:
        assert c.post(f"/api/vol/meets/{sid}", headers=tma(P), json={"team": True}).status_code == 200
    return sid


def _present(con, sid, vid):
    con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at) VALUES (?, ?, ?)", (vid, sid, int(time.time()) - 3600))


def _finish(con, sid, ago):
    con.execute("UPDATE qr_sessions SET started_at = ?, ended_at = ? WHERE id = ?", (int(time.time()) - ago - 3600, int(time.time()) - ago, sid))


def _misses(c, tg=P):
    return {r["id"]: r["misses"] for r in c.get("/api/vol", headers=tma(tg)).json()["people"]}


def test_misses_count_only_for_a_held_teambuilding(zz):
    c, _, con, org = zz
    vol.apply(con, org, vol.plan(_book()), "list")
    ids = [r[0] for r in con.execute("SELECT id FROM vol_people ORDER BY id")]
    assert len(ids) == 4
    sid = _meet(c, con, org)                       # frozen: the 4 imported + the President's own record = 5
    assert con.execute("SELECT expected_n FROM vol_meets WHERE session_id = ?", (sid,)).fetchone()[0] == 5
    late = con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, 'Late', 0)", (org,)).lastrowid
    _present(con, sid, ids[0]), _present(con, sid, ids[1])
    _finish(con, sid, 3600)
    assert set(_misses(c).values()) == {0}                                    # 2 marked < 3: never held, no misses
    _present(con, sid, ids[2])
    con.execute("UPDATE qr_sessions SET ended_at = NULL WHERE id = ?", (sid,))
    assert set(_misses(c).values()) == {0}                                    # not finished
    _finish(con, sid, 60)
    assert set(_misses(c).values()) == {0}                                    # finished, still inside GRACE
    _finish(con, sid, vol.GRACE + 60)
    m = _misses(c)
    assert m[ids[3]] == 1 and m[ids[0]] == m[ids[1]] == m[ids[2]] == 0 and m[late] == 0   # joined after the freeze: no miss
    meet = next(x for x in c.get("/api/vol", headers=tma(P)).json()["meets"] if x["session"] == sid)
    assert meet == {**meet, "held": True, "expected": 5, "marked": 3, "team": True}
    assert c.post(f"/api/vol/meets/{sid}", headers=tma(P), json={"team": False}).status_code == 200
    assert set(_misses(c).values()) == {0}                                    # not a teambuilding: no misses


def test_quarter_of_the_expected(zz):
    c, _, con, org = zz
    for i in range(19):                                                        # 19 + the President = 20 expected: 5 needed
        con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, ?, 0)", (org, f"P{i}"))
    sid = _meet(c, con, org)
    ids = [r[0] for r in con.execute("SELECT vol_id FROM vol_expected WHERE session_id = ? ORDER BY vol_id", (sid,))]
    for x in ids[:4]:
        _present(con, sid, x)
    _finish(con, sid, vol.GRACE + 60)
    assert sum(_misses(c).values()) == 0
    _present(con, sid, ids[4])
    assert sum(_misses(c).values()) == 15


def test_hours_from_check_in_and_out(zz):
    c, _, con, org = zz
    uid = _member(c, con, org, 3, "vika")
    sid = _meet(c, con, org, team=False, title="Concert")
    p = c.post(f"/api/screens/{sid}/start", headers=tma(P)).json()
    p = c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]
    assert _scan(c, 3, p).status_code == 200
    h = con.execute("SELECT h.* FROM vol_shifts h JOIN vol_people v ON v.id = h.vol_id WHERE v.user_id = ?", (uid,)).fetchone()
    assert h["session_id"] == sid and h["out_at"] is None and h["in_by"] == uid
    mine = c.get("/api/me", headers=tma(3)).json()["vol"]
    assert mine["mine"]["minutes"] == 0 and mine["mine"]["open"] == 1 and not mine["ledger"]   # never checked out: 0 minutes
    con.execute("UPDATE vol_shifts SET in_at = in_at - 5400 WHERE id = ?", (h["id"],))       # arrived 1.5 h ago
    c.post(f"/api/screens/{sid}/out", headers=tma(P))
    assert _scan(c, 3, p).status_code == 200
    _agree(c, 3)
    mine = c.get("/api/vol/mine", headers=tma(3)).json()
    assert mine["minutes"] == 90 and mine["open"] == 0 and len(mine["shifts"]) == 1 and "raw" not in mine
    login(c, 4, "guest")                                                                      # not in the club: no record
    assert _scan(c, 4, c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]).status_code in (200, 400)
    assert con.execute("SELECT COUNT(*) FROM vol_people WHERE user_id = ?", (_uid(c, 4),)).fetchone()[0] == 0


def test_teambuilding_gives_no_hours(zz):
    """Owner, Nov 10: hours are for volunteering at events; a teambuilding counts for misses only."""
    c, _, con, org = zz
    vid = con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, 'V', 0)", (org,)).lastrowid
    tb, ev = _meet(c, con, org), _meet(c, con, org, team=False, title="Concert")
    for sid in (tb, ev):
        con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, out_at) VALUES (?, ?, 0, 3600)", (vid, sid))
    p = c.get(f"/api/vol/people/{vid}", headers=tma(P)).json()
    assert p["minutes"] == 60 and len(p["shifts"]) == 2                       # the event's hour; the teambuilding's 0
    assert c.post(f"/api/vol/meets/{ev}", headers=tma(P), json={"team": True}).status_code == 200
    assert c.get(f"/api/vol/people/{vid}", headers=tma(P)).json()["minutes"] == 0


def test_who_reads_and_who_edits(zz):
    c, _, con, org = zz
    vol.apply(con, org, vol.plan(_book()), "list")
    vid = con.execute("SELECT id FROM vol_people WHERE tg = 'bek_test'").fetchone()[0]
    head = _member(c, con, org, 5, "head", "head")
    me3 = _member(c, con, org, 3, "vika")
    login(c, 6, "out")
    for tg in (5, 3, 6):                                                          # a Head, a member, a stranger: no ledger
        assert c.get("/api/vol", headers=tma(tg)).status_code == 403
        assert c.get(f"/api/vol/people/{vid}", headers=tma(tg)).status_code == 403
    assert c.post("/api/vol/access", headers=tma(5), json={"user": me3, "on": True}).status_code == 403
    assert c.post("/api/vol/access", headers=tma(P), json={"user": _uid(c, 6), "on": True}).status_code == 400  # not in the club
    assert c.post("/api/vol/access", headers=tma(P), json={"user": head, "on": True}).status_code == 200
    _agree(c, 5)
    seen = c.get(f"/api/vol/people/{vid}", headers=tma(5)).json()
    assert seen["raw"][MEM][KURS] == "3"                                          # granted: reads, columns included
    t = int(time.time())
    hid = con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at) VALUES (?, ?, ?)", (vid, t - 7200, t - 3600)).lastrowid  # an old hand-made one
    assert c.patch(f"/api/vol/shifts/{hid}", headers=tma(5), json={"gone": True, "reason": "duplicate"}).status_code == 403   # but never edits
    assert c.patch(f"/api/vol/shifts/{hid}", headers=tma(P), json={"gone": True, "reason": ""}).status_code == 400  # a reason is a must
    assert c.patch(f"/api/vol/shifts/{hid}", headers=tma(P), json={"gone": True, "reason": "duplicate"}).json()["minutes"] == 0
    assert c.patch(f"/api/vol/shifts/{hid}", headers=tma(P), json={"gone": False, "reason": "it was real"}).json()["minutes"] == 60
    got = c.post(f"/api/vol/people/{vid}/misses", headers=tma(P), json={"n": 1, "reason": "missed the meeting"}).json()
    assert got["misses"] == 1
    got = c.post(f"/api/vol/misses/{got['manual'][0]['id']}/drop", headers=tma(P), json={"reason": "typo"}).json()
    assert got["misses"] == 0
    edits = got["edits"]
    assert [e["what"] for e in edits] == ["miss_gone", "miss", "shift", "shift"]
    assert all("+7" not in str(e) for e in edits)
    own = c.get("/api/me", headers=tma(P)).json()["vol"]
    assert own["edit"] and own["ledger"] and own["mine"] is None
    assert c.post("/api/vol/access", headers=tma(P), json={"user": head, "on": False}).status_code == 200
    assert c.get("/api/vol", headers=tma(5)).status_code == 403


def test_link_merge_and_own_view(zz):
    c, _, con, org = zz
    vol.apply(con, org, vol.plan(_book()), "list")
    aru = con.execute("SELECT id FROM vol_people WHERE tg = 'aru_t'").fetchone()[0]
    nobody = con.execute("SELECT id FROM vol_people WHERE tg = 'nobody1'").fetchone()[0]
    uid = _member(c, con, org, 3, "aru")
    assert c.get("/api/vol/mine", headers=tma(3)).status_code == 404               # nothing of mine yet
    assert c.post(f"/api/vol/people/{aru}/link", headers=tma(3), json={"user": uid}).status_code == 403
    assert c.post(f"/api/vol/people/{aru}/link", headers=tma(P), json={"user": uid}).status_code == 200
    con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at) VALUES (?, 0, 1200)", (nobody,))
    con.execute("UPDATE vol_people SET balance = 60 WHERE id = ?", (nobody,))
    assert c.post(f"/api/vol/people/{nobody}/link", headers=tma(P), json={"user": uid}).status_code == 200   # the duplicate row merges
    assert con.execute("SELECT COUNT(*) FROM vol_people WHERE id IN (?, ?)", (aru, nobody)).fetchone()[0] == 1
    _agree(c, 3)
    mine = c.get("/api/vol/mine", headers=tma(3)).json()
    assert mine["minutes"] == 60 + 20 and "raw" not in mine and "edits" not in mine
    other = con.execute("SELECT id FROM vol_people WHERE tg = 'bek_test'").fetchone()[0]
    assert c.get(f"/api/vol/people/{other}", headers=tma(3)).status_code == 403    # only my own
    left = mine["id"]
    assert c.post(f"/api/vol/people/{left}/link", headers=tma(P), json={"user": None}).status_code == 200    # unlinked again
    assert c.get("/api/vol/mine", headers=tma(3)).status_code == 404 and "vol" not in c.get("/api/me", headers=tma(3)).json()


def test_autolink_by_telegram_username(zz):
    c, _, con, org = zz
    vol.apply(con, org, vol.plan(_book()), "list")
    aru = con.execute("SELECT id FROM vol_people WHERE tg = 'aru_t'").fetchone()[0]
    uid = _member(c, con, org, 3, "aru")
    other = _member(c, con, org, 4, "bek")
    con.execute("UPDATE users SET tg_username = 'Aru_T' WHERE id = ?", (uid,))
    con.execute("UPDATE users SET tg_username = 'nobody_here' WHERE id = ?", (other,))
    stray = login(c, 6, "x") and _uid(c, 6)  # not a member: never linked
    con.execute("UPDATE users SET tg_username = 'bek_test' WHERE id = ?", (stray,))
    assert vol.autolink(con, org) == 1 and vol.autolink(con, org) == 0
    assert con.execute("SELECT user_id FROM vol_people WHERE id = ?", (aru,)).fetchone()[0] == uid
    assert con.execute("SELECT user_id FROM vol_people WHERE tg = 'bek_test'").fetchone()[0] is None
    assert con.execute("SELECT actor_id FROM audit_log WHERE action = 'vol_link'").fetchone()[0] is None


def test_deleting_an_account_takes_its_record(zz):
    c, cfg, con, org = zz
    vol.apply(con, org, vol.plan(_book()), "list")
    aru = con.execute("SELECT id FROM vol_people WHERE tg = 'aru_t'").fetchone()[0]
    uid = _member(c, con, org, 3, "aru")
    c.post(f"/api/vol/people/{aru}/link", headers=tma(P), json={"user": uid})
    c.post("/api/vol/access", headers=tma(P), json={"user": uid, "on": True})
    con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at, in_by) VALUES (?, 0, 60, ?)", (aru, uid))
    other = con.execute("SELECT id FROM vol_people WHERE tg = 'bek_test'").fetchone()[0]
    con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at, in_by) VALUES (?, 0, 60, ?)", (other, uid))  # a shift she marked
    assert ("vol_people", "user_id") in logic._DEL_GONE and ("vol_access", "user_id") in logic._DEL_GONE
    delete_now(c, cfg, tma(3))
    assert con.execute("SELECT COUNT(*) FROM vol_people WHERE id = ?", (aru,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM vol_shifts WHERE vol_id = ?", (aru,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM vol_access").fetchone()[0] == 0
    assert con.execute("SELECT in_by FROM vol_shifts WHERE vol_id = ?", (other,)).fetchone()[0] is None


def test_admin_command(zz, monkeypatch, tmp_path, capsys):
    from kbtu import admin
    c, cfg, con, org = zz
    monkeypatch.setattr(admin.config, "load", lambda: dataclasses.replace(cfg, volunteers="zhzh"))
    f = tmp_path / "list.xlsx"
    f.write_bytes(_book())
    admin.main(["vol", "import", str(f), "--balance", "Total"])
    out = capsys.readouterr().out
    assert "dry run" in out and "people 4" in out and "+7000" not in out and "Aru" not in out
    assert con.execute("SELECT COUNT(*) FROM vol_people").fetchone()[0] == 0
    with pytest.raises(SystemExit):
        admin.main(["vol", "import", str(f), "--apply"])                         # where the list came from is a must
    admin.main(["vol", "import", str(f), "--apply", "--source", "list given by the club's president on 2026-11-06, evening"])
    assert "4 added" in capsys.readouterr().out
    admin.main(["vol", "import", str(f), "--apply", "--source", "again"])
    assert "imported already" in capsys.readouterr().out
    admin.main(["vol", "batches"])
    bid = capsys.readouterr().out.split()[0]
    admin.main(["vol", "undo", bid])
    assert "'gone': 4" in capsys.readouterr().out and con.execute("SELECT COUNT(*) FROM vol_people").fetchone()[0] == 0


def test_consent_only_for_whom_it_concerns(zz):
    """+vol1: asked of the people the ledger concerns (linked, granted, the President), nobody else; the routes hold it."""
    c, _, con, org = zz
    plain = c.get("/api/me", headers=tma(P)).json()["consentNow"]
    assert plain == logic.CONSENT + logic.account.CONSENT_VOL
    uid = _member(c, con, org, 3, "aru")
    login(c, 4, "other")
    assert not c.get("/api/me", headers=tma(4)).json()["consentNow"].endswith("+vol1")      # an ordinary student: nothing new
    assert not c.get("/api/me", headers=tma(3)).json()["consentNow"].endswith("+vol1")      # a member not linked yet: neither
    vid = con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, 'A', 0)", (org,)).lastrowid
    assert c.post(f"/api/vol/people/{vid}/link", headers=tma(P), json={"user": uid}).status_code == 200
    asked = c.get("/api/me", headers=tma(3)).json()["consentNow"]
    assert asked.endswith("+vol1")
    r = c.get("/api/vol/mine", headers=tma(3))
    assert r.status_code == 403 and r.json()["message"] == "consent"                         # held server-side until agreed
    _agree(c, 3)
    assert c.get("/api/vol/mine", headers=tma(3)).status_code == 200


def test_unlinked_before_deletion_still_goes(zz):
    c, cfg, con, org = zz
    vol.apply(con, org, vol.plan(_book()), "list")
    aru = con.execute("SELECT id FROM vol_people WHERE tg = 'aru_t'").fetchone()[0]
    uid = _member(c, con, org, 3, "aru")
    c.post(f"/api/vol/people/{aru}/link", headers=tma(P), json={"user": uid})
    c.post(f"/api/vol/people/{aru}/link", headers=tma(P), json={"user": None})                # unlinked just before
    delete_now(c, cfg, tma(3))
    assert con.execute("SELECT COUNT(*) FROM vol_people WHERE id = ?", (aru,)).fetchone()[0] == 0
    got = vol.apply(con, org, vol.plan(_book([["Eve Test", "1", "", "@eve_test"]])), "a later list")  # back on a newer list?
    assert got["deleted"] == 1 and got["added"] == 1                                            # never: only Eve is new
    assert con.execute("SELECT COUNT(*) FROM vol_people WHERE tg = 'aru_t'").fetchone()[0] == 0
    assert "aru" not in str([tuple(r) for r in con.execute("SELECT * FROM vol_gone")])         # a keyed hash, not the key


def test_access_ends_with_membership(zz):
    c, _, con, org = zz
    uid = _member(c, con, org, 5, "vice", "vice")
    c.post("/api/vol/access", headers=tma(P), json={"user": uid, "on": True})
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (org, uid))
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, uid))  # back by a link
    assert con.execute("SELECT COUNT(*) FROM vol_access").fetchone()[0] == 0
    assert c.get("/api/vol", headers=tma(5)).status_code == 403


def test_namesake_with_another_telegram_stays_apart():
    book = xlsx.write({MEM: [[FIO_LAT, TG], ["Aru Test", "@aru_t"]], HRS: [[FIO, TG2], ["Aru Test", "@aru_other"]]})
    assert len(vol.plan(book)["people"]) == 2


def test_merge_keeps_aliases(zz):
    c, _, con, org = zz
    vol.apply(con, org, vol.plan(_book(), "Total"), "list")
    aru, nobody = (con.execute("SELECT id FROM vol_people WHERE tg = ?", (x,)).fetchone()[0] for x in ("aru_t", "nobody1"))
    uid = _member(c, con, org, 3, "aru")
    c.post(f"/api/vol/people/{aru}/link", headers=tma(P), json={"user": uid})
    c.post(f"/api/vol/people/{nobody}/link", headers=tma(P), json={"user": uid})               # merged: one record
    n = con.execute("SELECT COUNT(*) FROM vol_people").fetchone()[0]
    got = vol.apply(con, org, vol.plan(_book([["Eve Test", "1", "", "@eve_test"]]), "Total"), "a later list")
    assert (got["added"], got["there"]) == (1, 4) and con.execute("SELECT COUNT(*) FROM vol_people").fetchone()[0] == n + 1  # Aru's row isn't back
    assert c.get("/api/vol/people/" + str(nobody), headers=tma(P)).json()["balance"] == 750 + 120    # her balances once each


def test_overlapping_shifts_count_once(zz):
    c, _, con, org = zz
    vid = con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, 'V', 0)", (org,)).lastrowid
    a, b = _meet(c, con, org, team=False, title="A"), _meet(c, con, org, team=False, title="B")
    con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, out_at) VALUES (?, ?, 0, 3600)", (vid, a))
    con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, out_at) VALUES (?, ?, 1800, 5400)", (vid, b))
    con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, out_at) VALUES (?, NULL, 600, 1200)", (vid,))
    assert c.get(f"/api/vol/people/{vid}", headers=tma(P)).json()["minutes"] == 90


def test_a_deletion_never_flips_a_held_teambuilding(zz):
    c, cfg, con, org = zz
    for i in range(3):
        con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, ?, 0)", (org, f"P{i}"))
    uid = _member(c, con, org, 3, "aru")
    sid = _meet(c, con, org)                                                   # 5 expected: 3 needed
    ids = [r[0] for r in con.execute("SELECT vol_id FROM vol_expected WHERE session_id = ? ORDER BY vol_id", (sid,))]
    mine = con.execute("SELECT id FROM vol_people WHERE user_id = ?", (uid,)).fetchone()[0]
    for x in [mine] + [i for i in ids if i != mine][:2]:
        _present(con, sid, x)
    _finish(con, sid, vol.GRACE + 60)
    assert sum(_misses(c).values()) == 2
    delete_now(c, cfg, tma(3))                                                 # one of the three who came
    assert sum(_misses(c).values()) == 2


def test_old_or_refused_scan_opens_no_shift(zz):
    c, cfg, con, org = zz
    uid = _member(c, con, org, 3, "vika")
    sid = _meet(c, con, org, team=False, title="Concert")
    c.post(f"/api/screens/{sid}/start", headers=tma(P))
    p = c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]
    assert _scan(c, 3, p).status_code == 200
    c.post(f"/api/screens/{sid}/out", headers=tma(P))
    assert _scan(c, 3, c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]).status_code == 200
    c.post(f"/api/screens/{sid}/in", headers=tma(P))
    _, s, slot, sig = p.split("_")
    old = f"ci_{s}_{int(slot) - 100}_{checkin._sig(cfg.token_key, f'ci.{s}.{int(slot) - 100}')}"
    _scan(c, 3, old)                                                           # an old link from the chat
    assert con.execute("SELECT COUNT(*) FROM vol_shifts h JOIN vol_people v ON v.id = h.vol_id WHERE v.user_id = ?", (uid,)).fetchone()[0] == 1


def test_zip_bombs_refused():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:                 # one part named by many sheets
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        z.writestr("xl/workbook.xml", f"<workbook {ns}><sheets>" + "".join(f'<sheet name="s{i}" r:id="r1"/>' for i in range(500)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData/></worksheet>")
    with pytest.raises(xlsx.Bad):
        xlsx.read(buf.getvalue())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:                 # small packed, huge unpacked
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/big.xml", b"\0" * (xlsx.MAX_ALL + 1))
    with pytest.raises(xlsx.Bad):
        xlsx.read(buf.getvalue())


def test_a_deleted_duplicate_row_stays_gone(zz):
    """A repeated row of the sheet is a record of its own with its own key: deleted with an account, never back."""
    c, cfg, con, org = zz
    dup = [["Aru Test", "2", "+70000000009", "@aru_t"]]
    vol.apply(con, org, vol.plan(_book(dup)), "list")
    second = con.execute("SELECT id FROM vol_people WHERE raw LIKE '%+70000000009%'").fetchone()[0]
    uid = _member(c, con, org, 3, "aru")
    c.post(f"/api/vol/people/{second}/link", headers=tma(P), json={"user": uid})
    delete_now(c, cfg, tma(3))
    got = vol.apply(con, org, vol.plan(_book(dup + [["Eve Test", "1", "", "@eve_test"]])), "a later list")
    assert (got["added"], got["deleted"]) == (1, 1)
    assert con.execute("SELECT COUNT(*) FROM vol_people WHERE raw LIKE '%+70000000009%'").fetchone()[0] == 0


def test_an_ambiguous_name_matches_nobody():
    """Two Aru Tests on the members sheet (the first without a Telegram): hours by @ go to the right one, by name to neither."""
    book = xlsx.write({MEM: [[FIO_LAT, TG], ["Aru Test", ""], ["Aru Test", "@aru_two"]],
                       HRS: [[FIO, TG2, "Total"], ["Aru Test", "@aru_two", "10"], ["Aru Test", "", "3"]]})
    p = vol.plan(book, "Total")
    by = {(r["tg"], tuple(sorted(r["sheets"]))): r["balance"] for r in p["people"]}
    assert len(p["people"]) == 3 and by[("aru_two", tuple(sorted((HRS, MEM))))] == 600
    assert by[(None, (MEM,))] == 0 and by[(None, (HRS,))] == 180


# ------------------------------------------------------------ hours only from scans; the unmarked; the door by a link (Nov 11)

def _door(c, sid, tg=P):
    """Start (once) and the QR this person shows."""
    c.post(f"/api/screens/{sid}/start", headers=tma(tg))
    return c.post(f"/api/screens/{sid}/show", headers=tma(tg)).json()["param"]


def _shift(con, uid, sid):
    return con.execute("SELECT h.* FROM vol_shifts h JOIN vol_people v ON v.id = h.vol_id WHERE v.user_id = ? AND h.session_id = ?", (uid, sid)).fetchone()


def _mins(c, tg):
    return c.get("/api/me", headers=tma(tg)).json()["vol"]["mine"]


def test_nobody_types_hours(zz, monkeypatch):
    """No route and no CLI command sets minutes, a shift's times or a balance: for the President, a Vice, a reader, the
    volunteer and the app's admin alike."""
    from kbtu import admin
    c, cfg, con, org = zz
    _member(c, con, org, 5, "vice", "vice")
    reader = _member(c, con, org, 6, "reader")
    me3 = _member(c, con, org, 3, "vika")
    login(c, 7, "boss")
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (_uid(c, 7),))
    assert c.post("/api/vol/access", headers=tma(P), json={"user": reader, "on": True}).status_code == 200
    vid = con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, 'V', 0)", (org,)).lastrowid
    assert c.post(f"/api/vol/people/{vid}/link", headers=tma(P), json={"user": me3}).status_code == 200
    t = int(time.time())
    hid = con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at) VALUES (?, ?, ?)", (vid, t - 7200, t - 3600)).lastrowid
    for tg in (P, 5, 6, 3, 7):
        if tg != 7:
            _agree(c, tg)
        h = tma(tg)
        assert c.post(f"/api/vol/people/{vid}/shifts", headers=h, json={"inAt": t - 900, "outAt": t - 60, "reason": "camera broke"}).status_code in (404, 405)
        assert c.post(f"/api/vol/people/{vid}/balance", headers=h, json={"minutes": 6000, "reason": "old sheet"}).status_code in (404, 405)
        for body in ({"outAt": t, "reason": "left late"}, {"inAt": t - 86000, "reason": "came early"}, {"minutes": 999, "reason": "more"}):
            assert c.patch(f"/api/vol/shifts/{hid}", headers=h, json=body).status_code in (400, 403)
        assert c.patch(f"/api/vol/shifts/{hid}", headers=h, json={"gone": False, "inAt": t - 86000, "outAt": t, "reason": "smuggled"}).status_code in (200, 403)
        assert c.post(f"/api/vol/shifts/{hid}/resolve", headers=h, json={"left": t}).status_code in (403, 404, 409)  # no session: nothing to answer for
    assert tuple(con.execute("SELECT in_at, out_at FROM vol_shifts WHERE id = ?", (hid,)).fetchone()) == (t - 7200, t - 3600)
    assert con.execute("SELECT balance FROM vol_people WHERE id = ?", (vid,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM vol_shifts").fetchone()[0] == 1
    paths = {(m, r.path) for r in c.app.routes if "/vol/" in getattr(r, "path", "") for m in r.methods}
    assert not any("balance" in p or p.endswith("/shifts") for _, p in paths)
    monkeypatch.setattr(admin.config, "load", lambda: dataclasses.replace(cfg, volunteers="zhzh"))
    for cmd in (["vol", "shift", str(vid), "60"], ["vol", "balance", str(vid), "600"], ["vol", "hours", str(vid), "10"], ["vol", "resolve", str(hid)]):
        with pytest.raises(SystemExit):
            admin.main(cmd)
    assert con.execute("SELECT balance FROM vol_people WHERE id = ?", (vid,)).fetchone()[0] == 0


def test_vice_is_president(zz):
    c, _, con, org = zz
    vice = _member(c, con, org, 5, "vice", "vice")
    me3 = _member(c, con, org, 3, "vika")
    _agree(c, 5)
    h = tma(5)
    assert c.get("/api/me", headers=h).json()["vol"]["edit"] and c.get("/api/vol", headers=h).json()["edit"]
    vid = con.execute("INSERT INTO vol_people (org_id, name, created_at) VALUES (?, 'V', 0)", (org,)).lastrowid
    assert c.get(f"/api/vol/people/{vid}", headers=h).status_code == 200
    assert c.post(f"/api/vol/people/{vid}/link", headers=h, json={"user": me3}).status_code == 200
    assert c.post("/api/vol/access", headers=h, json={"user": me3, "on": True}).json()["access"][0]["id"] == me3
    sid = checkin.new(con, "Teambuilding", [], org)
    assert c.post(f"/api/vol/meets/{sid}", headers=h, json={"team": True}).status_code == 200
    assert c.post(f"/api/vol/people/{vid}/misses", headers=h, json={"n": 1, "reason": "missed the meeting"}).json()["misses"] == 1
    assert c.post(f"/api/vol/meets/{sid}/hand", headers=h).status_code == 200
    assert c.get(f"/api/vol/meets/{sid}/door", headers=h).json()["lead"]
    con.execute("UPDATE org_members SET role = 'head' WHERE user_id = ?", (vice,))
    assert c.get("/api/vol", headers=h).status_code == 403                      # the role, not the person


def test_finish_leaves_the_unmarked_to_be_answered_for(zz):
    c, _, con, org = zz
    u3, u4 = _member(c, con, org, 3, "vika"), _member(c, con, org, 4, "bek")
    vice = _member(c, con, org, 5, "vice", "vice")
    reader = _member(c, con, org, 6, "reader")
    c.post("/api/vol/access", headers=tma(P), json={"user": reader, "on": True})
    login(c, 8, "stranger")
    sid = _meet(c, con, org, team=False, title="Concert")
    p = _door(c, sid)
    for tg in (3, 4, 5):                                                        # the Vice came as a volunteer: he runs nothing
        assert _scan(c, tg, p).status_code == 200
    con.execute("UPDATE vol_shifts SET in_at = in_at - 7200 WHERE session_id = ?", (sid,))
    h3, h4, h5 = (_shift(con, u, sid) for u in (u3, u4, vice))
    for tg in (3, 4, 5, 6):
        _agree(c, tg)
    assert c.post(f"/api/vol/shifts/{h3['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 409   # not finished yet
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(P)).status_code == 200
    end = con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert [_shift(con, u, sid)["out_at"] for u in (u3, u4, vice)] == [None] * 3   # nobody is closed by Finish itself
    assert _mins(c, 3) == {**_mins(c, 3), "minutes": 0, "open": 1, "unmarked": 0}
    assert next(m for m in c.get("/api/vol", headers=tma(P)).json()["meets"] if m["session"] == sid)["unresolved"] == 3
    door = c.get(f"/api/vol/meets/{sid}/door", headers=tma(P)).json()
    assert [(x["id"], x["inAt"], x["outAt"]) for x in door["unmarked"]] == [(h["id"], h["in_at"], None) for h in (h3, h4, h5)] and door["ended"] == end
    for tg in (3, 6, 8):                                                        # a volunteer, a reader, a stranger: not theirs
        assert c.get(f"/api/vol/meets/{sid}/door", headers=tma(tg)).status_code == 403
        assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(tg), json={"left": None}).status_code == 403
    assert c.post(f"/api/vol/shifts/{h5['id']}/resolve", headers=tma(5), json={"left": None}).json()["message"] == "own"   # never one's own
    assert _shift(con, u4, sid)["out_at"] is None and _shift(con, vice, sid)["out_at"] is None
    # "was here until the end": to Finish
    assert c.post(f"/api/vol/shifts/{h3['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 200
    assert _shift(con, u3, sid)["out_at"] == end and _mins(c, 3)["minutes"] == (end - h3["in_at"]) // 60 >= 120
    # "left at T": only from the check-in to Finish
    for bad in (h4["in_at"] - 120, end + 60, "18:30", True, 1.5):
        assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(5), json={"left": bad}).status_code == 400
    assert _shift(con, u4, sid)["out_at"] is None
    assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(5), json={"left": h4["in_at"] + 1800}).status_code == 200   # the Vice answers too
    assert _mins(c, 4) == {**_mins(c, 4), "minutes": 30, "open": 0, "unmarked": 1}
    e = con.execute("SELECT * FROM vol_edits WHERE what = 'resolve' AND ref = ?", (h4["id"],)).fetchone()
    assert e["by"] == vice and e["reason"] == "" and __import__("json").loads(e["new"]) == {"out": h4["in_at"] + 1800, "left_unmarked": True, "until_end": False}
    # the counter: in the ledger's row, on the person's page, on my own hours; no minutes taken off
    rows_ = {r["id"]: r["unmarked"] for r in c.get("/api/vol", headers=tma(6)).json()["people"]}
    assert rows_[h3["vol_id"]] == rows_[h4["vol_id"]] == 1 and rows_[h5["vol_id"]] == 0
    mine = c.get("/api/vol/mine", headers=tma(4)).json()
    assert mine["unmarked"] == 1 and mine["shifts"][0]["unmarked"] and mine["minutes"] == 30
    # answered wrongly: answered again, the counter stays one
    assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 200
    assert _mins(c, 4)["unmarked"] == 1 and _shift(con, u4, sid)["out_at"] == end
    assert c.post(f"/api/vol/shifts/{h5['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 200
    assert c.get(f"/api/vol/meets/{sid}/door", headers=tma(P)).json()["unmarked"][0]["outAt"] == end
    # a shift closed by its own check-out scan is nobody's to answer for
    hid = con.execute("INSERT INTO vol_shifts (vol_id, session_id, in_at, out_at) VALUES (?, ?, ?, ?)", (h3["vol_id"], sid, end - 600, end - 300)).lastrowid
    assert c.post(f"/api/vol/shifts/{hid}/resolve", headers=tma(P), json={"left": None}).status_code == 409


def test_who_runs_the_door_is_on_shift_from_the_first_mark(zz):
    c, cfg, con, org = zz
    pres = _uid(c, P)
    u3 = _member(c, con, org, 3, "vika")
    vice = _member(c, con, org, 5, "vice", "vice")
    sid = _meet(c, con, org, team=False, title="Concert")
    p = _door(c, sid)
    assert _shift(con, pres, sid) is None                                      # showing the QR alone opens nothing
    assert _scan(c, 3, p).status_code == 200
    mine, hers = _shift(con, u3, sid), _shift(con, pres, sid)
    assert hers["in_at"] == mine["in_at"] and hers["in_by"] == pres and hers["out_at"] is None
    assert _shift(con, vice, sid) is None                                      # the Vice ran nothing here
    assert _scan(c, 5, p).status_code == 200                                   # he comes as a volunteer...
    con.execute("UPDATE vol_shifts SET in_at = in_at - 3600 WHERE session_id = ?", (sid,))
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(5)).status_code == 200   # ...and presses Finish
    end = con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert _shift(con, pres, sid)["out_at"] == end                             # who started it: there to the end
    assert _shift(con, vice, sid)["out_at"] is None and _shift(con, u3, sid)["out_at"] is None   # pressing Finish earns nothing
    assert con.execute("SELECT COUNT(*) FROM vol_edits WHERE what = 'resolve'").fetchone()[0] == 0   # no "left unmarked" for them
    # her own check-out comes first
    sid2 = _meet(c, con, org, team=False, title="Fair")
    p = _door(c, sid2)
    assert _scan(c, 3, p).status_code == 200
    c.post(f"/api/screens/{sid2}/out", headers=tma(P))
    con.execute("UPDATE vol_shifts SET in_at = in_at - 3600 WHERE session_id = ?", (sid2,))
    assert _scan(c, P, c.post(f"/api/screens/{sid2}/show", headers=tma(P)).json()["param"]).json()["left"]
    out = _shift(con, pres, sid2)["out_at"]
    con.execute("UPDATE vol_shifts SET out_at = out_at - 600 WHERE session_id = ? AND out_at IS NOT NULL", (sid2,))
    c.post(f"/api/screens/{sid2}/finish", headers=tma(P))
    assert out is not None and _shift(con, pres, sid2)["out_at"] == out - 600 and _shift(con, u3, sid2)["out_at"] is None
    assert _scan(c, 5, _signed(cfg, sid2, int(time.time()) // checkin.SLOT)).status_code != 200   # leaving without having come: still refused


def test_the_door_handed_over_by_a_link(zz):
    c, cfg, con, org = zz
    u3, u4 = _member(c, con, org, 3, "vika"), _member(c, con, org, 4, "bek")
    _member(c, con, org, 5, "vice", "vice")
    login(c, 8, "stranger")
    sid, other = _meet(c, con, org, team=False, title="Concert"), _meet(c, con, org, team=False, title="Fair")
    for tg in (3, 4, 5):
        _agree(c, tg)                                                                   # on the roster now: the ledger's part of the policy
    assert c.post(f"/api/vol/meets/{sid}/hand", headers=tma(3)).status_code == 403      # only the President and Vice make it
    assert c.post(f"/api/screens/{sid}/start", headers=tma(3)).status_code == 403
    got = c.post(f"/api/vol/meets/{sid}/hand", headers=tma(P)).json()
    tok = got["token"]
    assert got["hand"] == {"holder": None} and len(tok) >= 32
    dump = "".join(str(tuple(r)) for t in ("vol_hands", "audit_log", "meta") for r in con.execute(f"SELECT * FROM {t}"))
    assert tok not in dump                                                              # hashed, never logged
    assert c.post("/api/vol/hand", headers=tma(8), json={"token": tok}).status_code == 403   # not in the club
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok[:-1] + "x"}).status_code == 404
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": None}).status_code == 404
    assert c.post("/api/vol/hand", headers=tma(5), json={"token": tok}).json()["session"] == sid    # the Vice looks: takes nothing
    assert c.get(f"/api/vol/meets/{sid}/door", headers=tma(P)).json()["hand"] == {"holder": None}
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok}).json()["session"] == sid
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok}).status_code == 200          # mine: opened again
    assert c.post("/api/vol/hand", headers=tma(4), json={"token": tok}).status_code == 409          # one-time
    assert c.post(f"/api/screens/{sid}/start", headers=tma(4)).status_code == 403
    assert c.get(f"/api/vol/meets/{sid}/door", headers=tma(5)).json()["hand"]["holder"]["id"] == u3  # who holds it
    # this session's door, nothing else
    assert sid in [x["session"] for x in c.get("/api/screens", headers=tma(3)).json()]
    p = _door(c, sid, 3)
    assert p and c.post(f"/api/screens/{sid}/out", headers=tma(3)).status_code == 200 and c.post(f"/api/screens/{sid}/in", headers=tma(3)).status_code == 200
    for method, path in (("post", f"/api/screens/{sid}/csv"), ("post", f"/api/screens/{sid}/unpair"), ("post", f"/api/screens/{sid}/helpers"),
                         ("delete", f"/api/screens/{sid}/helpers"), ("post", f"/api/screens/{other}/start"), ("post", f"/api/screens/{other}/finish"),
                         ("get", "/api/vol"), ("post", f"/api/vol/meets/{sid}/hand"), ("delete", f"/api/vol/meets/{sid}/hand"),
                         ("get", f"/api/vol/meets/{other}/door"), ("post", f"/api/vol/meets/{other}/hand")):
        assert getattr(c, method)(path, headers=tma(3)).status_code == 403, path
    assert c.post(f"/api/vol/meets/{sid}", headers=tma(3), json={"team": True}).status_code == 403
    assert _scan(c, 4, p).status_code == 200
    h4 = _shift(con, u4, sid)
    mine = _shift(con, u3, sid)
    assert mine["in_at"] == h4["in_at"] and mine["in_by"] == u3                         # running the door: on shift from the first mark
    con.execute("UPDATE vol_shifts SET in_at = in_at - 3600 WHERE session_id = ?", (sid,))
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(3)).status_code == 200
    end = con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert _shift(con, u3, sid)["out_at"] == end
    door = c.get(f"/api/vol/meets/{sid}/door", headers=tma(3)).json()
    assert [x["id"] for x in door["unmarked"]] == [h4["id"]] and door["hand"] is None and not door["lead"]
    assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(3), json={"left": end - 60}).status_code == 200
    assert c.post(f"/api/vol/meets/{sid}/hand", headers=tma(P)).status_code == 409      # finished: no new link
    # it ends GRACE after Finish
    con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ?", (int(time.time()) - vol.GRACE - 60, sid))
    assert c.get(f"/api/vol/meets/{sid}/door", headers=tma(3)).status_code == 403
    assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(3), json={"left": None}).status_code == 403
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok}).status_code == 404
    assert sid not in [x["session"] for x in c.get("/api/screens", headers=tma(3)).json()]
    # taken back; a new link ends the last; leaving the club ends it
    old = c.post(f"/api/vol/meets/{other}/hand", headers=tma(5)).json()["token"]        # the Vice makes one too
    tok2 = c.post(f"/api/vol/meets/{other}/hand", headers=tma(P)).json()["token"]
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": old}).status_code == 404
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok2}).status_code == 200
    assert c.post(f"/api/screens/{other}/start", headers=tma(3)).status_code == 200
    assert c.delete(f"/api/vol/meets/{other}/hand", headers=tma(P)).json()["hand"] is None
    assert c.post(f"/api/screens/{other}/show", headers=tma(3)).status_code == 403
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok2}).status_code == 404
    tok3 = c.post(f"/api/vol/meets/{other}/hand", headers=tma(P)).json()["token"]
    assert c.post("/api/vol/hand", headers=tma(4), json={"token": tok3}).status_code == 200
    con.execute("UPDATE vol_hands SET created_at = created_at - ? WHERE user_id = ?", (vol.HAND_MAX + 60, u4))
    assert c.post(f"/api/screens/{other}/show", headers=tma(4)).status_code == 403      # never finished: the link still dies
    con.execute("UPDATE vol_hands SET created_at = ? WHERE user_id = ?", (int(time.time()), u4))
    assert c.post(f"/api/screens/{other}/show", headers=tma(4)).status_code == 200
    con.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (org, u4))
    assert c.post(f"/api/screens/{other}/show", headers=tma(4)).status_code == 403
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, u4))
    assert ("vol_hands", "user_id") in logic._DEL_GONE
    delete_now(c, cfg, tma(4))                                                          # an account deleted: its right goes with it
    assert con.execute("SELECT COUNT(*) FROM vol_hands WHERE user_id = ?", (u4,)).fetchone()[0] == 0


# ------------------------------------------------------------ the adversarial review's probes (Nov 11)

def test_no_shift_counts_more_than_twelve_hours(zz):
    """A session left open for days, then Finish: nobody gets days of hours, by a scan, by running the door or by an answer."""
    c, _, con, org = zz
    pres, u3, u4 = _uid(c, P), _member(c, con, org, 3, "vika"), _member(c, con, org, 4, "bek")
    sid = _meet(c, con, org, team=False, title="Left open")
    p = _door(c, sid)
    assert _scan(c, P, p).status_code == 200 and _scan(c, 3, p).status_code == 200   # she checks herself in with her own QR
    con.execute("UPDATE vol_shifts SET in_at = in_at - 10 * 86400 WHERE session_id = ?", (sid,))
    con.execute("UPDATE qr_sessions SET started_at = started_at - 10 * 86400 WHERE id = ?", (sid,))
    assert _scan(c, 4, c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]).status_code == 200   # ten days into it
    assert c.post(f"/api/screens/{sid}/finish", headers=tma(P)).status_code == 200
    for tg in (3, 4):
        _agree(c, tg)
    assert _mins(c, P)["minutes"] == vol.SHIFT_CAP // 60
    h3, h4 = _shift(con, u3, sid), _shift(con, u4, sid)
    assert c.post(f"/api/vol/shifts/{h3['id']}/resolve", headers=tma(P), json={"left": h3["in_at"] + vol.SHIFT_CAP + 60}).status_code == 400
    assert c.post(f"/api/vol/shifts/{h3['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 200
    assert _shift(con, u3, sid)["out_at"] == h3["in_at"] + vol.SHIFT_CAP and _mins(c, 3)["minutes"] == vol.SHIFT_CAP // 60
    assert c.post(f"/api/vol/shifts/{h4['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 200
    assert _mins(c, 4)["minutes"] == 0                                         # past 12 h after Start: the session gives no more hours
    con.execute("UPDATE vol_shifts SET out_at = in_at + 5 * 86400 WHERE id = ?", (h3["id"],))   # whatever a row says
    assert _mins(c, 3)["minutes"] == vol.SHIFT_CAP // 60
    assert c.get("/api/vol/mine", headers=tma(3)).json()["shifts"][0]["outAt"] == h3["in_at"] + vol.SHIFT_CAP
    assert pres


def test_only_start_or_pairing_runs_the_door(zz):
    c, _, con, org = zz
    pres = _uid(c, P)
    vice = _member(c, con, org, 5, "vice", "vice")
    _member(c, con, org, 3, "vika")
    sid = _meet(c, con, org, team=False, title="Concert")
    c.post(f"/api/screens/{sid}/start", headers=tma(P))
    for act in ("start", "show", "out", "in", "show"):                         # the Vice taps everything after her Start
        assert c.post(f"/api/screens/{sid}/{act}", headers=tma(5)).status_code == 200
    assert _scan(c, 3, c.post(f"/api/screens/{sid}/show", headers=tma(5)).json()["param"]).status_code == 200
    assert _shift(con, pres, sid) is not None and _shift(con, vice, sid) is None
    sid2 = _meet(c, con, org, team=False, title="Fair")                        # pairing the screen is running it
    c.post(f"/api/screens/{sid2}/start", headers=tma(P))
    code = c.post("/api/screen/pair").json()["code"]
    assert c.post("/api/screens/bind", headers=tma(5), json={"code": code, "session": sid2}).status_code == 200
    assert _scan(c, 3, c.post(f"/api/screens/{sid2}/show", headers=tma(P)).json()["param"]).status_code == 200
    assert _shift(con, vice, sid2) is not None
    c.post(f"/api/screens/{sid2}/finish", headers=tma(5))
    log = [(r["action"], r["actor_id"], r["target"]) for r in con.execute("SELECT * FROM audit_log WHERE action LIKE 'vol_session_%' AND target = ? ORDER BY id", (f"qr:{sid2}",))]
    assert log == [("vol_session_start", pres, f"qr:{sid2}"), ("vol_session_finish", vice, f"qr:{sid2}")]
    d = __import__("json").loads(con.execute("SELECT data FROM audit_log WHERE action = 'vol_session_finish'").fetchone()[0])
    assert set(d) == {"duration"} and 0 <= d["duration"] < 60


def test_never_ones_own_shift_even_unlinked(zz):
    c, _, con, org = zz
    pres = _uid(c, P)
    _member(c, con, org, 5, "vice", "vice")
    sid = _meet(c, con, org, team=False, title="X")
    c.post(f"/api/screens/{sid}/start", headers=tma(5))                        # the Vice runs it; she comes as a volunteer
    assert _scan(c, P, c.post(f"/api/screens/{sid}/show", headers=tma(5)).json()["param"]).status_code == 200
    con.execute("UPDATE vol_shifts SET in_at = in_at - 7200 WHERE session_id = ?", (sid,))
    c.post(f"/api/screens/{sid}/finish", headers=tma(5))
    h = _shift(con, pres, sid)
    assert h["out_at"] is None
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(P), json={"left": None}).json()["message"] == "own"
    assert c.post(f"/api/vol/people/{h['vol_id']}/link", headers=tma(P), json={"user": None}).status_code == 200
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(P), json={"left": None}).json()["message"] == "own"
    assert con.execute("SELECT out_at FROM vol_shifts WHERE id = ?", (h["id"],)).fetchone()[0] is None


def test_no_shift_after_finish(zz):
    c, _, con, org = zz
    u3 = _member(c, con, org, 3, "vika")
    sid = _meet(c, con, org, team=False, title="Y")
    p = _door(c, sid)
    _scan(c, 3, p)
    c.post(f"/api/screens/{sid}/out", headers=tma(P))
    p2 = c.post(f"/api/screens/{sid}/show", headers=tma(P)).json()["param"]
    _scan(c, 3, p2)                                                            # checked out properly
    c.post(f"/api/screens/{sid}/finish", headers=tma(P))
    _scan(c, 3, p2)                                                            # scanned again after Finish, inside GRACE
    got = con.execute("SELECT out_at FROM vol_shifts h JOIN vol_people v ON v.id = h.vol_id WHERE v.user_id = ? AND session_id = ?", (u3, sid)).fetchall()
    assert len(got) == 1 and got[0][0] is not None


def test_answers_only_for_new_sessions_and_a_week(zz):
    c, _, con, org = zz
    u3, u4 = _member(c, con, org, 3, "vika"), _member(c, con, org, 4, "bek")
    sid = _meet(c, con, org, team=False, title="Concert")
    tok = c.post(f"/api/vol/meets/{sid}/hand", headers=tma(P)).json()["token"]
    for tg in (3, 4):
        _agree(c, tg)
    assert c.post("/api/vol/hand", headers=tma(4), json={"token": tok}).status_code == 200
    assert _scan(c, 3, _door(c, sid)).status_code == 200
    c.post(f"/api/screens/{sid}/finish", headers=tma(P))
    h = _shift(con, u3, sid)
    end = con.execute("SELECT ended_at FROM qr_sessions WHERE id = ?", (sid,)).fetchone()[0]
    since = con.execute("SELECT value FROM meta WHERE key = ?", (vol.FROM,)).fetchone()[0]
    assert int(since) <= end
    con.execute("UPDATE meta SET value = ? WHERE key = ?", (str(end + 1), vol.FROM))      # finished before the feature came
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 409
    assert c.get(f"/api/vol/meets/{sid}/door", headers=tma(P)).json()["unmarked"] == []
    assert next(m for m in c.get("/api/vol", headers=tma(P)).json()["meets"] if m["session"] == sid)["unresolved"] == 0
    con.execute("UPDATE meta SET value = ? WHERE key = ?", (since, vol.FROM))
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(4), json={"left": None}).status_code == 200    # the holder answers once
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(4), json={"left": end}).status_code == 409    # again: the President's or Vice's
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(P), json={"left": end}).status_code == 200
    con.execute("UPDATE meta SET value = '0' WHERE key = ?", (vol.FROM,))
    con.execute("UPDATE qr_sessions SET ended_at = ? WHERE id = ?", (int(time.time()) - vol.RESOLVE_FOR - 60, sid))   # a week on
    assert c.post(f"/api/vol/shifts/{h['id']}/resolve", headers=tma(P), json={"left": None}).status_code == 409
    assert u4


def test_a_shift_taken_out_is_shown_to_its_volunteer(zz):
    c, _, con, org = zz
    u3 = _member(c, con, org, 3, "vika")
    vid = con.execute("INSERT INTO vol_people (org_id, user_id, created_at) VALUES (?, ?, 0)", (org, u3)).lastrowid
    hid = con.execute("INSERT INTO vol_shifts (vol_id, in_at, out_at) VALUES (?, 0, 3600)", (vid,)).lastrowid
    _agree(c, 3)
    assert c.patch(f"/api/vol/shifts/{hid}", headers=tma(P), json={"gone": True, "reason": "a duplicate"}).status_code == 200
    mine = c.get("/api/vol/mine", headers=tma(3)).json()
    assert mine["minutes"] == 0 and mine["shifts"] == [{**mine["shifts"][0], "id": hid, "gone": True, "goneReason": "a duplicate"}]


def test_a_manual_student_does_not_burn_the_link(zz):
    c, _, con, org = zz
    u3, u4 = _member(c, con, org, 3, "vika"), _member(c, con, org, 4, "bek")
    sid = _meet(c, con, org, team=False, title="Concert")
    tok = c.post(f"/api/vol/meets/{sid}/hand", headers=tma(P)).json()["token"]
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (u3,))
    assert c.post("/api/vol/hand", headers=tma(3), json={"token": tok}).status_code in (401, 403)
    assert con.execute("SELECT user_id FROM vol_hands").fetchone()[0] is None
    _agree(c, 4)
    assert c.post("/api/vol/hand", headers=tma(4), json={"token": tok}).status_code == 200 and u4
