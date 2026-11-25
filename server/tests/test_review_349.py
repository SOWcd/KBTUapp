"""Inkar's server review, part 2 (issue #349): each fix with the case that broke it."""
from __future__ import annotations

import io
import logging
import time
import zipfile

import pytest

from kbtu import db, logic, xlsx
from kbtu.logic import donations, fchannel, helpus, profiles
from test_core import env, login, set_clock, tma  # noqa: F401  (env: the fixture)

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
RELS = f'<Relationships xmlns="{P}"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>'
BOOK = f'<workbook xmlns="{M}" xmlns:r="{R}"><sheets><sheet name="A" r:id="r1"/></sheets></workbook>'


def test_one_failing_sweep_skips_no_other(env, monkeypatch, caplog):
    """1: stats_day marks its day first, so a sweep that raised used to skip every later one (the policy's retention
    among them) till tomorrow. Now each runs on its own, an open transaction is rolled back, the failure is logged."""
    _, cfg = env
    con = db.connect(cfg.db_path)
    t = int(time.time())
    set_clock(monkeypatch, lambda: (t + 5 * 3600) // 86400 * 86400 - 5 * 3600 + 600)  # 00:10 in Almaty

    def boom(c):
        c.execute("BEGIN IMMEDIATE")  # dies mid-transaction: the next sweeps must not run inside it
        raise PermissionError("receipts")
    ran = []
    monkeypatch.setattr(donations, "sweep", boom)
    monkeypatch.setattr(helpus, "sweep", lambda c: ran.append(c.in_transaction))  # one after it
    with caplog.at_level(logging.ERROR):
        logic.stats_day(con)
    assert ran == [False] and not con.in_transaction
    assert "stats_day" in caplog.text and "boom" in caplog.text
    assert con.execute("SELECT 1 FROM stats_days").fetchone()  # the night's row is there all the same


def test_lost_post_goes_again_only_when_asked(env, monkeypatch):
    """2: a post whose send got no answer may be in the channel already, untracked; releasing it puts a second copy
    there that the app can't take down. As replies: refused without again=True, by the logic and the route."""
    c, cfg = env
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (bob["id"],))
    pid = con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'hello all', 1, 'held', 'lost', 0)",
                      (ann["id"],)).lastrowid
    mod = logic.Viewer(bob["id"], "moderator", True)
    with pytest.raises(logic.ApiError) as e:
        fchannel.mod_decide(con, mod, pid, True)
    assert (e.value.code, e.value.message) == ("conflict", "lost")
    with pytest.raises(logic.ApiError):
        fchannel.mod_decide(con, mod, pid, True, "yes")  # only a real true
    assert con.execute("SELECT status, why FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[:] == ("held", "lost")
    fchannel.mod_decide(con, mod, pid, True, True)
    assert con.execute("SELECT status, why FROM fchan_posts WHERE id = ?", (pid,)).fetchone()[:] == ("live", None)
    # a lost one may still be removed without asking; a held one that isn't lost goes out as before
    lost = con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'b', 0, 'held', 'lost', 0)", (ann["id"],)).lastrowid
    fchannel.mod_decide(con, mod, lost, False)
    held = con.execute("INSERT INTO fchan_posts (user_id, body, anon, status, why, created_at) VALUES (?, 'c', 0, 'held', 'person', 0)", (ann["id"],)).lastrowid
    fchannel.mod_decide(con, mod, held, True)
    assert con.execute("SELECT status FROM fchan_posts WHERE id = ?", (held,)).fetchone()[0] == "live"


def _zip(parts: dict[str, bytes | str], method=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        for name, body in parts.items():
            z.writestr(name, body)
    return buf.getvalue()


def test_malformed_xlsx_is_bad():
    """4: read() promises Bad (admin.py catches only that), never a raw KeyError, ParseError, TypeError, ValueError or
    BadZipFile; and a DTD is refused in UTF-16 too, where a byte search for "<!ENTITY" can't see it."""
    sheet = f'<worksheet xmlns="{M}"><sheetData><row r="1"><c r="A1" t="s"><v>x</v></c></row></sheetData></worksheet>'
    cases = {
        "no rels": _zip({"xl/workbook.xml": BOOK}),
        "broken xml": _zip({"xl/workbook.xml": "<workbook", "xl/_rels/workbook.xml.rels": RELS}),
        "no sheets": _zip({"xl/workbook.xml": f'<workbook xmlns="{M}"/>', "xl/_rels/workbook.xml.rels": RELS}),
        "shared index not a number": _zip({"xl/workbook.xml": BOOK, "xl/_rels/workbook.xml.rels": RELS, "xl/worksheets/sheet1.xml": sheet}),
    }
    good = _zip({"xl/workbook.xml": BOOK, "xl/_rels/workbook.xml.rels": RELS,
                 "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{M}"><sheetData/></worksheet>'}, zipfile.ZIP_STORED)
    cases["crc"] = good.replace(b"<sheetData/>", b"<sheetDatb/>")  # stored, so the bytes change in place: a CRC mismatch
    for what, data in cases.items():
        with pytest.raises(xlsx.Bad):
            print(what)  # pytest shows it on a failure
            xlsx.read(data)
    utf16 = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE w [<!ENTITY a "aaaa">]>'
             f'<workbook xmlns="{M}"><sheets/></workbook>').encode("utf-16")
    assert b"<!ENTITY" not in utf16
    with pytest.raises(xlsx.Bad, match="DTD"):
        xlsx.read(_zip({"xl/workbook.xml": utf16, "xl/_rels/workbook.xml.rels": RELS}))
    assert xlsx.read(xlsx.write({"A": [["x", "y"], [], ["", "z"]]})) == ({"A": [["x", "y"], [], ["", "z"]]}, 0)


def test_fuel_medal_shows_no_payment_time(env):
    """5: Fuel is granted inside the Stars payment's transaction, so its reached_at is the second someone paid. Like
    Sponsor's, its date is never shown: not to friends who see a showcased one, not on one's own."""
    c, cfg = env
    ann = login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    profiles._grant(con, None, ann["id"], "supporter", log=False)
    fuel = {a["code"]: a for a in profiles.achievements(con, ann["id"], own=True)}["supporter"]
    assert fuel["level"] == 1 and fuel["at"] is None


def test_posts_scope_non_ascii_digit(env):
    """6: "org:" and a superscript two passed isdigit() and then broke int(): a 500. Now a 400, as any bad scope."""
    c, _ = env
    login(c, 1, "ann")
    assert c.get("/api/posts?scope=org:%C2%B2", headers=tma(1)).status_code == 400
    assert c.get("/api/posts?scope=org:%D9%A3", headers=tma(1)).status_code == 400  # an Arabic-Indic three
    assert c.get("/api/posts?scope=all", headers=tma(1)).status_code == 200
