"""Admissions (logic/ako.py): the applicant's link is the only credential (kept as a digest, never read back from a GET),
documents reach the org's own people alone and never the applicant again, interview seats can't be double-booked,
sending asks only for the first documents, the calendar invite, the managers' moves, and retention."""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path

from PIL import Image

from kbtu import db
from kbtu.logic import ako
from test_core import env, login, set_clock, tma  # noqa: F401  (env is a fixture)

HEAD, MEMBER, STRANGER = 11, 12, 13
TEAMS = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_x%40thread.v2/0"


def _jpeg(w=900, h=1200) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 236)).save(out, "JPEG")
    return out.getvalue()


def _pdf() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(out, "PDF")
    return out.getvalue()


def _day(t: int, days: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t + days * 86400 + 5 * 3600))


def _setup(env, monkeypatch):
    c, cfg = env
    t0 = int(time.time())
    set_clock(monkeypatch, lambda: t0)
    ids = {u: login(c, u, n)["id"] for u, n in ((HEAD, "head"), (MEMBER, "member"), (STRANGER, "stranger"))}
    con = db.connect(cfg.db_path)
    with db.tx(con):
        oid = con.execute("""INSERT INTO orgs (slug, kind, name, short, emoji, official, created_at)
            VALUES ('ako', 'office', 'AKO', 'A', 'briefcase_3d', 1, ?)""", (t0,)).lastrowid
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'head', ?), (?, ?, 'member', ?)",
                    (oid, ids[HEAD], t0, oid, ids[MEMBER], t0))
    ako.seed(con, oid)
    return c, cfg, con, oid, t0


def _new(c, oid, program="emba", name="Erlan S", phone="8 701 234 56 71") -> str:
    r = c.post(f"/api/orgs/{oid}/ako/apps", headers=tma(HEAD), json={"program": program, "name": name, "phone": phone})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _slots(c, oid, t0, times=("10:00", "10:30"), days=3, cap=1):
    r = c.post(f"/api/orgs/{oid}/ako/slots", headers=tma(HEAD), json={"day": _day(t0, days), "times": list(times), "minutes": 30,
                                                                        "cap": cap, "teams": TEAMS, "who": "Dr. A"})
    assert r.status_code == 204, r.text
    return [s["id"] for s in c.get(f"/api/orgs/{oid}/ako", headers=tma(HEAD)).json()["slots"]]


def test_public_link_makes_a_draft_only_on_a_post(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    page = c.get("/api/ako/o/ako")
    assert page.status_code == 200 and [p["key"] for p in page.json()["programs"]][:2] == ["mba", "mba-law"]
    assert c.get("/api/ako/o/nope").status_code == 404
    c.get("/ako/o/ako")  # the page itself, as a link preview fetches it
    assert con.execute("SELECT COUNT(*) FROM ako_apps").fetchone()[0] == 0
    r = c.get("/ako/whatever")
    assert r.headers["referrer-policy"] == "no-referrer" and "no-store" in r.headers["cache-control"] and r.headers["x-robots-tag"] == "noindex"
    tok = c.post("/api/ako/o/ako", json={"program": "dba", "lang": "en"}).json()["token"]
    row = con.execute("SELECT token, status, lang, ip FROM ako_apps").fetchone()
    assert row["token"] == hashlib.sha256(tok.encode()).digest() and tok.encode() not in bytes(row["token"])
    assert (row["status"], row["lang"]) == ("draft", "en") and row["ip"] and "testclient" not in row["ip"]
    assert c.post("/api/ako/o/ako", json={"program": "nope"}).status_code == 404
    monkeypatch.setattr(ako, "STARTS_A_DAY", 2)
    assert c.post("/api/ako/o/ako", json={"program": "dba"}).status_code == 200
    assert c.post("/api/ako/o/ako", json={"program": "dba"}).status_code == 429


def test_the_link_is_the_credential(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tok = _new(c, oid)
    v = c.get("/api/ako/a", headers={"X-Ako": tok}).json()
    assert (v["program"], v["name"], v["phone"], v["status"], v["consent"]) == ("emba", "Erlan S", "+77012345671", "draft", False)
    for bad in ("", "x" * 43, tok[:-1], tok + "a"):
        assert c.get("/api/ako/a", headers={"X-Ako": bad}).status_code == 404
    # a document waits for the notice agreed to
    assert c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": tok}, content=_jpeg()).status_code == 403
    assert c.patch("/api/ako/a", headers={"X-Ako": tok}, json={"consent": True, "email": "e@mail.kz"}).status_code == 204
    assert c.patch("/api/ako/a", headers={"X-Ako": tok}, json={"email": "nope"}).status_code == 400
    assert c.patch("/api/ako/a", headers={"X-Ako": tok}, json={"phone": "call me"}).status_code == 400
    f = c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": tok}, content=_jpeg(4000, 3000)).json()
    assert f["mime"] == "image/jpeg"
    path = Path(cfg.db_path).parent / "ako" / con.execute("SELECT path FROM ako_files WHERE id = ?", (f["id"],)).fetchone()[0]
    assert max(Image.open(path).size) == ako.SIDE  # re-encoded: no byte of the upload survives
    assert c.post("/api/ako/a/files?doc=diploma", headers={"X-Ako": tok}, content=_pdf()).json()["mime"] == "application/pdf"
    assert c.post("/api/ako/a/files?doc=diploma", headers={"X-Ako": tok}, content=b"%PDF-1.4 broken").status_code == 400
    assert c.post("/api/ako/a/files?doc=diploma", headers={"X-Ako": tok}, content=b"<html>").status_code == 400
    assert c.post("/api/ako/a/files?doc=passport", headers={"X-Ako": tok}, content=_jpeg()).status_code == 400
    assert c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": "y" * 43}, content=_jpeg()).status_code == 404
    # the applicant sees names and sizes, never a way to the contents
    v = c.get("/api/ako/a", headers={"X-Ako": tok}).json()
    assert [x["doc"] for x in v["files"]] == ["cv", "diploma"] and not any("path" in x or "url" in x for x in v["files"])
    # a page taken back is gone from the disk too
    assert c.delete(f"/api/ako/a/files/{f['id']}", headers={"X-Ako": tok}).status_code == 204 and not path.exists()
    assert c.delete(f"/api/ako/a/files/{f['id']}", headers={"X-Ako": tok}).status_code == 404
    monkeypatch.setattr(ako, "MAX_FILES", 2)
    assert c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": tok}, content=_jpeg()).status_code == 200
    assert c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": tok}, content=_jpeg()).status_code == 429
    assert len(list((Path(cfg.db_path).parent / "ako").rglob("*.*"))) == 2  # the refused one left nothing


def test_documents_reach_the_team_alone(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tok = _new(c, oid)
    c.patch("/api/ako/a", headers={"X-Ako": tok}, json={"consent": True})
    fid = c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": tok}, content=_jpeg()).json()["id"]
    aid = con.execute("SELECT id FROM ako_apps").fetchone()[0]
    for who in (HEAD, MEMBER):
        url = c.get(f"/api/orgs/{oid}/ako/files/{fid}/link", headers=tma(who)).json()["url"]
        r = c.get(url)  # no session: the signature is the key, for five minutes
        assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment;") and "no-store" in r.headers["cache-control"]
        assert c.get(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(who)).json()["files"][0]["doc"] == "cv"
    z = c.get(c.get(f"/api/orgs/{oid}/ako/apps/{aid}/link", headers=tma(MEMBER)).json()["url"])
    assert z.status_code == 200 and z.content[:2] == b"PK"
    url = c.get(f"/api/orgs/{oid}/ako/files/{fid}/link", headers=tma(HEAD)).json()["url"]
    assert c.get(url.replace(f"/f/{fid}?", f"/f/{fid + 1}?")).status_code == 404  # a signature names its one file
    assert c.get(url.replace("&s=", "&s=0")).status_code == 404 and c.get(f"/api/ako/f/{fid}").status_code == 404
    set_clock(monkeypatch, lambda: t0 + ako.LINK_TTL + 1)
    assert c.get(url).status_code == 404
    set_clock(monkeypatch, lambda: t0)
    for path in (f"/api/orgs/{oid}/ako", f"/api/orgs/{oid}/ako/apps/{aid}", f"/api/orgs/{oid}/ako/files/{fid}/link", f"/api/orgs/{oid}/ako/apps/{aid}/link"):
        assert c.get(path, headers=tma(STRANGER)).status_code == 403
        assert c.get(path, headers={"X-Ako": tok}).status_code in (401, 403)
    # a reviewer reads, never changes
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(MEMBER), json={"note": "x"}).status_code == 403
    assert c.post(f"/api/orgs/{oid}/ako/apps", headers=tma(MEMBER), json={"program": "mba"}).status_code == 403
    me = {m["org"]["id"]: m.get("ako") for m in c.get("/api/me", headers=tma(MEMBER)).json()["memberships"]}
    assert me[oid] == "review"
    assert {m["org"]["id"]: m.get("ako") for m in c.get("/api/me", headers=tma(HEAD)).json()["memberships"]}[oid] == "manage"


def test_one_seat_one_person(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    s1, s2 = _slots(c, oid, t0)
    a, b = _new(c, oid), _new(c, oid, name="Gulnara A")
    v = c.post("/api/ako/a/slot", headers={"X-Ako": a}, json={"slot": s1}).json()
    assert v["slot"]["id"] == s1 and v["slot"]["teams"] == TEAMS
    assert c.post("/api/ako/a/slot", headers={"X-Ako": b}, json={"slot": s1}).status_code == 409
    assert [s["id"] for s in c.get("/api/ako/a", headers={"X-Ako": b}).json()["slots"]] == [s2]  # a full time isn't offered
    # moving frees the old seat in the same write
    assert c.post("/api/ako/a/slot", headers={"X-Ako": a}, json={"slot": s2}).json()["slot"]["id"] == s2
    assert c.post("/api/ako/a/slot", headers={"X-Ako": b}, json={"slot": s1}).status_code == 200
    # a program without an interview has no times
    assert c.post("/api/ako/a/slot", headers={"X-Ako": _new(c, oid, program="mini-mba")}, json={"slot": s1}).status_code == 400
    # the cutoff: inside it, neither booking nor giving back by hand
    first = min(x["at"] for x in c.get(f"/api/orgs/{oid}/ako", headers=tma(HEAD)).json()["slots"])
    set_clock(monkeypatch, lambda: first - ako.CUTOFF + 60)
    late = _new(c, oid, name="Late")
    for slot in (s1, s2):
        assert c.post("/api/ako/a/slot", headers={"X-Ako": late}, json={"slot": slot}).status_code in (409,)
    assert c.post("/api/ako/a/slot", headers={"X-Ako": a}, json={"slot": None}).status_code == 409


def test_a_removed_time_asks_its_people_to_pick_again(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    s1, s2 = _slots(c, oid, t0)
    a = _new(c, oid)
    c.post("/api/ako/a/slot", headers={"X-Ako": a}, json={"slot": s1})
    r = c.delete(f"/api/orgs/{oid}/ako/slots/{s1}", headers=tma(HEAD))
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    assert c.delete(f"/api/orgs/{oid}/ako/slots/{s1}?force=true&reason=The%20panel%20moved", headers=tma(HEAD)).json() == {"booked": 1}
    v = c.get("/api/ako/a", headers={"X-Ako": a}).json()
    assert v["slot"] is None and v["rebook"] == "The panel moved" and [s["id"] for s in v["slots"]] == [s2]
    assert c.post("/api/ako/a/slot", headers={"X-Ako": a}, json={"slot": s2}).json()["rebook"] is None
    # the team moves someone, even over the cutoff, but never over a seat; taking a time away needs a reason
    b = _new(c, oid, name="B")
    bid = con.execute("SELECT id FROM ako_apps WHERE name = 'B'").fetchone()[0]
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{bid}", headers=tma(HEAD), json={"slot": s2}).status_code == 409
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{bid}", headers=tma(HEAD), json={"slot": None}).status_code == 200
    aid = con.execute("SELECT id FROM ako_apps WHERE slot_id = ?", (s2,)).fetchone()[0]
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"slot": None}).status_code == 400
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"slot": None, "reason": "Ill"}).status_code == 200
    assert c.get("/api/ako/a", headers={"X-Ako": a}).json()["rebook"] == "Ill"
    del b


def test_sending_asks_only_for_the_first_documents(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    s1, _ = _slots(c, oid, t0)
    tok = _new(c, oid, name="")
    h = {"X-Ako": tok}
    r = c.post("/api/ako/a/submit", headers=h)
    assert r.status_code == 400 and r.json()["error"] == "bad_input"
    c.patch("/api/ako/a", headers=h, json={"consent": True, "name": "Erlan Saparov"})
    c.post("/api/ako/a/files?doc=cv", headers=h, content=_jpeg())
    r = c.post("/api/ako/a/submit", headers=h)
    assert r.status_code == 400 and r.json()["missing"] == ["diploma"]
    c.post("/api/ako/a/files?doc=diploma", headers=h, content=_pdf())
    assert c.post("/api/ako/a/submit", headers=h).json()["error"] == "bad_input"  # a time to pick, and none picked
    c.post("/api/ako/a/slot", headers=h, json={"slot": s1})
    v = c.post("/api/ako/a/submit", headers=h).json()
    assert v["status"] == "sent" and v["sentAt"] == t0
    assert con.execute("SELECT ip FROM ako_apps").fetchone()[0] is None
    # later documents come by the same link; a sent package keeps its program
    assert c.post("/api/ako/a/files?doc=med", headers=h, content=_jpeg()).status_code == 200
    assert c.patch("/api/ako/a", headers=h, json={"program": "dba"}).status_code == 409
    ics = c.get("/api/ako/a/ics", headers=h)
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    body = ics.text.replace("\r\n ", "")
    assert "TRIGGER:-P1D" in body and "TRIGGER:-PT1H" in body and TEAMS.replace(",", "\\,") in body and "DTSTART:" in body
    # a decided package is closed to the link
    aid = con.execute("SELECT id FROM ako_apps").fetchone()[0]
    for status in ("review", "accepted"):
        assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"status": status}).status_code == 200
    assert c.post("/api/ako/a/files?doc=photo", headers=h, content=_jpeg()).status_code == 409
    # a program without an interview sends with nothing first asked
    t2 = _new(c, oid, program="mini-mba")
    c.patch("/api/ako/a", headers={"X-Ako": t2}, json={"consent": True})
    assert c.post("/api/ako/a/submit", headers={"X-Ako": t2}).json()["status"] == "sent"


def test_a_new_link_stops_the_old_one_and_a_drop_takes_the_files(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    old = _new(c, oid)
    c.patch("/api/ako/a", headers={"X-Ako": old}, json={"consent": True})
    c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": old}, content=_jpeg())
    aid = con.execute("SELECT id FROM ako_apps").fetchone()[0]
    new = c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"newLink": True}).json()["token"]
    assert c.get("/api/ako/a", headers={"X-Ako": old}).status_code == 404
    assert c.get("/api/ako/a", headers={"X-Ako": new}).status_code == 200
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"status": "review"}).status_code == 400  # a draft
    folder = Path(cfg.db_path).parent / "ako"
    assert list(folder.rglob("*.jpg"))
    assert c.delete(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD)).status_code == 204
    assert not list(folder.rglob("*.jpg")) and c.get("/api/ako/a", headers={"X-Ako": new}).status_code == 404


def test_teams_links_are_microsofts(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    day = _day(t0, 4)
    for bad in ("https://evil.example/teams", "http://teams.microsoft.com/l/x", "javascript:alert(1)"):
        assert c.post(f"/api/orgs/{oid}/ako/slots", headers=tma(HEAD), json={"day": day, "times": ["10:00"], "teams": bad}).status_code == 400
    assert c.post(f"/api/orgs/{oid}/ako/slots", headers=tma(HEAD), json={"day": _day(t0, -1), "times": ["10:00"]}).status_code == 400
    assert c.put(f"/api/orgs/{oid}/ako/days", headers=tma(HEAD), json={"day": day, "teams": TEAMS}).status_code == 204
    assert c.get(f"/api/orgs/{oid}/ako", headers=tma(HEAD)).json()["days"] == {day: TEAMS}


def test_retention(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    draft, sent = _new(c, oid), _new(c, oid, program="mini-mba")
    for t in (draft, sent):
        c.patch("/api/ako/a", headers={"X-Ako": t}, json={"consent": True})
        c.post("/api/ako/a/files?doc=cv", headers={"X-Ako": t}, content=_jpeg())
    c.post("/api/ako/a/submit", headers={"X-Ako": sent})
    folder = Path(cfg.db_path).parent / "ako"
    set_clock(monkeypatch, lambda: t0 + ako.DRAFT_KEEP + 1)
    ako.sweep(con)
    assert c.get("/api/ako/a", headers={"X-Ako": draft}).status_code == 404 and len(list(folder.rglob("*.jpg"))) == 1
    set_clock(monkeypatch, lambda: t0 + ako.KEEP + 1)
    ako.sweep(con)
    assert con.execute("SELECT COUNT(*) FROM ako_apps").fetchone()[0] == 0 and not list(folder.rglob("*.jpg"))
