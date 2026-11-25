"""The class timetable from the portal, schools."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sqlite3
import time
import types
from pathlib import Path

import pytest

from kbtu import bot, bot_dm, db, logic, texts
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_schools_seeded(env):
    """KBTU's schools come from its site once: crests, three languages; a school made by hand before is
    filled in, not doubled; an edit by hand drops that field's translations."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    got = con.execute("SELECT slug, name, i18n, logo_file_id, official FROM orgs WHERE kind = 'school' ORDER BY id").fetchall()
    assert len(got) == len(logic.SCHOOLS) == 11 and all(r["logo_file_id"] and r["official"] for r in got)
    site = next(r for r in got if r["slug"] == "site")
    assert json.loads(site["i18n"])["en"]["name"] == "School of Information Technology and Engineering"
    # run again: nothing doubles; a hand-made one before the seed is matched by name
    con.execute("DELETE FROM meta WHERE key = 'schools'")
    con.execute("UPDATE orgs SET name = 'School of Law', slug = 'handmade', logo_file_id = NULL, i18n = NULL WHERE slug = 'law'")
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    law = con.execute("SELECT * FROM orgs WHERE slug = 'handmade'").fetchone()
    assert con.execute("SELECT COUNT(*) FROM orgs WHERE kind = 'school'").fetchone()[0] == 11 and law["logo_file_id"] and law["i18n"]
    shown = logic.org_ref(con, law)
    assert shown["i18n"]["kk"]["name"] and shown["logo"] and shown["i18n"]["ru"]["abbr"] == "\u0428\u041f"
    # version 1 seeded before: the next brings the short names, the name the school typed stays
    con.execute("UPDATE meta SET value = '1' WHERE key = 'schools'")
    con.execute("UPDATE orgs SET name = 'Our Law', slug = 'law', i18n = NULL WHERE slug = 'handmade'")
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    law = con.execute("SELECT * FROM orgs WHERE slug = 'law'").fetchone()
    assert law["name"] == "Our Law" and json.loads(law["i18n"])["en"]["abbr"] == "SL"


def test_my_school(env):
    """Settings: my school over the list's (it can be wrong): a KBTU school's name as the app keeps it, or none;
    never free text, a club, or a guest's."""
    c, cfg = env
    login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    logic.seed_schools(con, Path(cfg.db_path).parent / "media")
    con.execute("INSERT INTO orgs (slug, kind, name, short, emoji, created_at) VALUES ('it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    sce = "\u0428\u043a\u043e\u043b\u0430 \u0445\u0438\u043c\u0438\u0447\u0435\u0441\u043a\u043e\u0439 \u0438\u043d\u0436\u0435\u043d\u0435\u0440\u0438\u0438"
    me = lambda body: c.patch("/api/me", headers=tma(10), json=body)
    con.execute("UPDATE students SET school = NULL WHERE user_id = (SELECT id FROM users WHERE tg_id = 10)")
    st = me({"school": sce}).json()["student"]
    assert st["school"] == sce and "school" in st["fixable"]                 # an empty one filled: the once kept
    for bad in ("Made Up School", "IT Club", 5, ["x"]):
        assert me({"school": bad}).status_code == 400
    assert c.get("/api/me", headers=tma(10)).json()["student"]["school"] == sce
    assert me({"school": None}).status_code == 400                           # no clearing (Nov 3: cleared by mistake)
    other = con.execute("SELECT name FROM orgs WHERE kind = 'school' AND name != ? LIMIT 1", (sce,)).fetchone()[0]
    st = me({"school": other}).json()["student"]
    assert st["school"] == other and "school" not in st["fixable"]           # a change: spent (review once-edit 4)
    assert me({"school": sce}).json()["student"]["school"] == sce          # back to the one before: free, once (Nov 3)
    assert me({"school": other}).json()["message"] == "fixed"                # then support
    con.execute("UPDATE students SET school = NULL WHERE user_id = (SELECT id FROM users WHERE tg_id = 10)")
    con.commit()                                                             # cleared before clearing was refused
    assert "school" in c.get("/api/me", headers=tma(10)).json()["student"]["fixable"]
    assert me({"school": sce}).json()["student"]["school"] == sce          # an empty one filled: free, even spent
    assert c.patch("/api/me", headers=tma(22, "Guest"), json={"school": sce}).status_code in (401, 403)


COURSES = ("Physical Education", "Imaginary Algebra", "History of Made-Up Things", "Unlabelled Long Course", "Unlabelled Short Course")


def portal_page(lang: str = "en") -> str:
    """tests/fixtures/portal_week.html (English) as the portal shows it in another language: its day names, the courses
    in made-up names ("Imaginary Algebra (kk)"); the rooms, times and kinds the same."""
    from kbtu import portal
    html = (Path(__file__).parent / "fixtures" / "portal_week.html").read_text(encoding="utf-8")
    if lang != "en":
        for i, day in ((0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (5, "Saturday")):
            html = html.replace(f">{day}<", f">{portal.DAY_NAMES[lang][i].title()}<")
        for name in COURSES:
            html = html.replace(f">{name}<", f">{name} ({lang})<")
    return html


def test_portal_schedule(env, monkeypatch):
    """The week from the portal's schedule page saved on the phone (PLAN 26): a Web Archive or an .mht sent to the bot.
    A made-up page (tests/fixtures/portal_week.html): the phone's one-day layout ignored, the days by name, times as
    written or from the pixels, no label: over 1 h 40 a lecture. Only a page with the student's own name is taken; the
    file isn't kept and the student ID on it is never stored."""
    import plistlib
    from email.message import EmailMessage
    from kbtu import portal
    page = (Path(__file__).parent / "fixtures" / "portal_week.html").read_bytes()
    archive = plistlib.dumps({"WebMainResource": {"WebResourceData": page, "WebResourceTextEncodingName": "UTF-8",
                                                   "WebResourceMIMEType": "text/html", "WebResourceURL": "https://uninet.kbtu.kz/student/schedule"}},
                             fmt=plistlib.FMT_BINARY)
    mht = EmailMessage()
    mht["MIME-Version"] = "1.0"
    mht.make_mixed()
    mht.add_attachment(page, maintype="text", subtype="html", disposition="inline")  # Chrome: UTF-8, no charset
    mht.add_attachment(b"\x89PNG", maintype="image", subtype="png")
    mht = mht.as_bytes().replace(b"multipart/mixed", b"multipart/related")
    want = [(1, "10:00", "11:40", "Physical Education", "practice", "Gym", "Coach Example"),
            (1, "14:00", "15:00", "Imaginary Algebra", "practice", "251", "Teacher One"),
            (3, "12:00", "14:00", "History of Made-Up Things", "lecture", "388", "Teacher Two"),
            (3, "15:00", "17:00", "Unlabelled Long Course", "lecture", "305", "Teacher Three"),
            (6, "08:00", "09:00", "Unlabelled Short Course", "practice", None, "Teacher Four")]
    for data in (page, archive, mht):
        w = portal.parse(portal.page_html(data))
        assert w.name == "Testov A." and [(x.weekday, x.begins, x.ends, x.subject, x.kind, x.room, x.teacher) for x in w.lessons] == want
    for bad in (b"%PDF-1.4", b"bplist00junk", b"<html><body>Grades</body></html>"):
        with pytest.raises(portal.NotSchedule):
            portal.parse(portal.page_html(bad))
    same = portal.same_person
    assert same("Testov A.", "Ali", "Testov") and same("Ali Testov", "Ali", "Testov") and same("Ali T.", "Ali", "Testov")
    assert same("\u0422\u0435\u0441\u0442\u043e\u0432 \u0410.", "Ali", "Testov")         # a Cyrillic page, a Latin Microsoft name
    assert same("Akhmetov A.", "\u0410\u043b\u0430\u043d", "\u0410\u0445\u043c\u0435\u0442\u043e\u0432") and same("Yerlan Zh.", "\u0415\u0440\u043b\u0430\u043d", "\u0416\u0430\u043d\u043e\u0432")  # passport Latin
    assert not same("Testov B.", "Ali", "Testov") and not same("Other A.", "Ali", "Testov") and not same(None, "Ali", "Testov")

    c, cfg = env
    login(c, 50, "ali")                                                  # Ali Testov
    login(c, 51, "bek")                                                  # Bek Testov: someone else
    _con = db.connect(cfg.db_path)  # the page's own ID (00X000000): here only the schedule changes
    _con.execute("UPDATE students SET student_id = '00X000000' WHERE user_id = (SELECT id FROM users WHERE tg_id = 50)")
    _con.close()
    files = {"F1": archive, "F2": mht, "F3": b"<html><body>no grid</body></html>", "F4": portal_page("ru").encode(),
             "F5": portal_page("kk").replace("10:00&ndash;11:40", "11:00&ndash;12:40").encode()}           # in Kazakh, PE an hour later
    class Resp:
        def __init__(self, body):
            self.body, self.content = body, body if isinstance(body, bytes) else b""
        def json(self):
            return self.body
    class Http:
        async def get(self, url, params=None):
            if url.endswith("/getFile"):
                return Resp({"ok": True, "result": {"file_path": params["file_id"]}})
            return Resp(files[url.rsplit("/", 1)[1]])
    con = db.connect(cfg.db_path)
    def send(tg, fid, name="Schedule.webarchive", size=7_000_000):
        msg = {"message_id": 1, "from": {"id": tg}, "chat": {"id": tg, "type": "private"}, "date": logic.now(),
               "document": {"file_id": fid, "file_name": name, "file_size": size}}
        assert bot_dm._sched_file(msg)
        return asyncio.run(bot_dm._schedule(cfg, Http(), con, msg))["text"]
    assert send(99, "F1") == texts.bot_message("ru", "sched_signin")[0]
    assert send(51, "F1") == texts.bot_message("ru", "sched_other")[0]            # Bek sends Ali's page: refused
    assert [x["subject"] for x in c.get("/api/me/schedule", headers=tma(51)).json()] == ["Calculus"]   # his own stays
    assert send(50, "F3", "page.html") == texts.bot_message("ru", "sched_not")[0]
    assert send(50, "F3", "file") == texts.bot_message("ru", "sched_not")[0]      # "file": sniffed, not a page
    m = {"from": {"id": 50}, "chat": {"id": 50, "type": "private"}, "document": {"file_id": "F1", "file_name": "file", "mime_type": "application/octet-stream"}}
    assert bot_dm._sched_file(m) and not bot_dm._sched_file({**m, "chat": {"id": -5, "type": "group"}})
    assert not bot_dm._sched_file({**m, "document": {**m["document"], "mime_type": "application/pdf"}})
    assert send(50, "F1", size=30_000_000) == texts.bot_message("ru", "sched_big")[0]
    assert c.delete("/api/me/schedule", headers=tma(50)).status_code == 204                 # login()'s class gone: his first week
    assert send(50, "F1", "Schedule_webarchive") == texts.bot_message("ru", "sched_ok", n=5)[0]   # iOS: the dot came as "_"
    assert bot_dm._sched_file({"document": {"file_name": "x", "mime_type": "application/x-webarchive"}})  # or only its type
    assert not bot_dm._sched_file({"document": {"file_name": "receipt.pdf", "mime_type": "application/pdf"}})
    got = c.get("/api/me/schedule", headers=tma(50)).json()
    assert [(x["weekday"], x["begins"], x["subject"], x["kind"]) for x in got] == [(w[0], w[1], w[3], w[4]) for w in want]
    # the page sent again: its language, then what changed in the week; counts and language names only
    said = lambda *parts: " ".join(texts.bot_message("ru", k, **f)[0] for k, f in parts)  # noqa: E731
    ru = texts.SCHED_LANG["ru"]
    assert send(50, "F2", "Schedule.mht") == said(("sched_same", {"language": ru["en"]}), ("sched_nochange", {}))  # from Android: not doubled
    assert len(c.get("/api/me/schedule", headers=tma(50)).json()) == 5
    assert send(50, "F2", "file") == said(("sched_same", {"language": ru["en"]}), ("sched_nochange", {}))  # nameless: sniffed as an .mht
    assert send(50, "F4") == said(("sched_added", {"language": ru["ru"], "languages": f"{ru['ru']}, {ru['en']}"}))
    assert send(50, "F5") == said(("sched_added", {"language": ru["kk"], "languages": f"{ru['ru']}, {ru['kk']}, {ru['en']}"}), ("sched_changed", {"n": 1}))
    assert send(50, "F5") == said(("sched_same", {"language": ru["kk"]}), ("sched_nochange", {}))
    got = c.get("/api/me/schedule", headers=tma(50)).json()
    assert [(x["begins"], x["subject"]) for x in got][:2] == [("11:00", "Physical Education (kk)"), ("14:00", "Imaginary Algebra (kk)")]
    assert got[0]["names"] == {"en": "Physical Education", "ru": "Physical Education (ru)", "kk": "Physical Education (kk)"}
    assert all(len(x["names"]) == 3 for x in got)
    dump = "\n".join(con.iterdump())
    assert "Phone Only Course" not in dump                                       # the phone layout ignored
    assert not bot_dm._sched_file({"document": {"file_name": "receipt.pdf"}})

    # the Week sheet's "Delete schedule": nothing of the week stays anywhere in the database; Bek's stays; again is fine;
    # a guest gets what the GET gives a guest: no error, no week
    assert c.delete("/api/me/schedule", headers=tma(50)).status_code == 204
    assert c.get("/api/me/schedule", headers=tma(50)).json() == []
    dump = "\n".join(con.iterdump())
    assert not [x for w in want for x in (w[3], w[6]) if x in dump]               # subjects, teachers: in no table at all
    assert c.delete("/api/me/schedule", headers=tma(50)).status_code == 204
    assert [x["subject"] for x in c.get("/api/me/schedule", headers=tma(51)).json()] == ["Calculus"]
    assert c.delete("/api/me/schedule", headers=tma(52)).status_code == 204 and c.get("/api/me/schedule", headers=tma(52)).json() == []


def test_schedule_page_sid(env):
    """The student ID on the page (the name matched): equal, nothing; another number of the same year and degree,
    written over silently with the audit line (old value); another year, left; held by another account, left and the
    founder gets a notice with no ID in it; five a day; an unconfirmed account's never."""
    c, cfg = env
    login(c, 50, "ali")
    login(c, 51, "bek")
    login(c, 52, "fon")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1, role = 'admin' WHERE tg_id = 52")
    con.execute("UPDATE students SET student_id = '24B000002' WHERE user_id = (SELECT id FROM users WHERE tg_id = 51)")
    uid = con.execute("SELECT id FROM users WHERE tg_id = 50").fetchone()[0]
    con.execute("UPDATE students SET student_id = '24B000009' WHERE user_id = ?", (uid,))
    sid = lambda: con.execute("SELECT student_id FROM students WHERE user_id = ?", (uid,)).fetchone()[0]  # noqa: E731
    audits = lambda: con.execute("SELECT data FROM audit_log WHERE action = 'identity_fix'").fetchall()  # noqa: E731

    class Resp:
        def __init__(self, body):
            self.body, self.content = body, body if isinstance(body, bytes) else b""
        def json(self):
            return self.body

    def send(x):
        class Http:
            async def get(self, url, params=None):
                if url.endswith("/getFile"):
                    return Resp({"ok": True, "result": {"file_path": "p"}})
                return Resp(portal_page().replace("00X000000", x).encode())
        msg = {"message_id": 1, "from": {"id": 50}, "chat": {"id": 50, "type": "private"}, "date": logic.now(),
               "document": {"file_id": "F", "file_name": "page.html", "file_size": 9000}}
        return asyncio.run(bot_dm._schedule(cfg, Http(), con, msg))["text"]
    send("24B000009")
    plain = send("24B000009")                                            # the week already in: the plain answer
    send("23B000001")                                                    # another year: left, a line says so
    assert sid() == "24B000009" and not audits()
    assert send("24B000001") == plain                                    # same year: written over, no extra word to the student
    assert sid() == "24B000001" and len(audits()) == 1
    assert '"old": "24B000009"' in audits()[0][0] and '"new": "24B000001"' in audits()[0][0]
    send("24B000001")                                                    # equal: nothing more
    assert len(audits()) == 1
    again = lambda: con.execute("UPDATE students SET fixed = '' WHERE user_id = ?", (uid,))  # noqa: E731  (support's `fix reset`: a page spends the once)
    again()
    send("24B000002")                                                     # held by Bek: unchanged, the founder told
    assert sid() == "24B000001" and len(audits()) == 1
    told = con.execute("SELECT b.ref, u.tg_id FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind = 'sid_page_clash'").fetchall()
    assert [t[1] for t in told] == [52] and "24B000002" not in told[0][0] and "24B000001" not in told[0][0]
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'sid_page_taken'").fetchone()[0] == 1
    for x in ("24B000003", "24B000004", "24B000005"):                   # 1 year + 1 fix + 1 taken + these: the 5th is the last
        again()
        send(x)
    assert sid() == "24B000004"
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM audit_log")
    send("24B000006")                                                    # unconfirmed: the name is self-typed
    assert sid() == "24B000004"


def test_schedule_languages(env):
    """The week sent again with the portal in another language (owner, Oct 30): the page's language by its day names;
    every page the truth about times, rooms and which classes there are; each class keeps its names in the languages
    sent before, found again by its name where it has one in the page's language, else by its place in the week (a
    page in another language has other words and no course code). No translation: only names the student's pages gave."""
    from kbtu import portal
    week = {x: portal.parse(portal_page(x)) for x in ("en", "ru", "kk")}
    assert {x: w.lang for x, w in week.items()} == {"en": "en", "ru": "ru", "kk": "kk"}
    assert portal.parse(re.sub(r">(Monday|Tuesday|Wednesday|Saturday)<", ">?<", portal_page())).lang is None  # day names it doesn't know
    phys, alg, hist, kaz = ("\u0424\u0438\u0437\u0438\u043a\u0430", "\u0410\u043b\u0433\u0435\u0431\u0440\u0430", "\u0422\u0430\u0440\u0438\u0445",
                            "\u049a\u0430\u0437\u0430\u049b \u0442\u0456\u043b\u0456")  # Fizika, Algebra; Tarikh, Qazaq tili (Kazakh's own letters)
    g = portal.guess_lang
    assert (g(["Calculus", "Physics"]), g([phys, alg]), g([phys, hist, kaz]), g(["101"]), g([])) == ("en", "ru", "kk", None, None)

    c, cfg = env
    ali, bek = login(c, 60, "ali"), login(c, 61, "bek")
    con = db.connect(cfg.db_path)
    def save(lessons, lang, uid=ali["id"]):
        with db.tx(con):
            return logic.save_schedule(con, uid, lessons, lang)
    def mine(tg=60):
        return [(x["weekday"], x["begins"], x["subject"], x["room"], x["names"]) for x in c.get("/api/me/schedule", headers=tma(tg)).json()]
    def named(name, *langs):
        return {x: name if x == "en" else f"{name} ({x})" for x in langs}
    def did(got):
        return got["added"], got["removed"], got["moved"]

    # Russian first: login()'s English Calculus goes (a removed class goes); then Kazakh: each class both names
    assert save(week["ru"].lessons, "ru") == {"lang": "ru", "was": 1, "had": ["en"], "has": ["ru"], "added": 5, "removed": 1, "moved": 0}
    assert save(week["kk"].lessons, "kk") == {"lang": "kk", "was": 5, "had": ["ru"], "has": ["ru", "kk"], "added": 0, "removed": 0, "moved": 0}
    assert [x[4] for x in mine()] == [named(n, "ru", "kk") for n in COURSES] and [x[2] for x in mine()] == [f"{n} (kk)" for n in COURSES]
    # English with PE an hour later: the new time, the names of all three
    later = portal.parse(portal_page().replace("10:00&ndash;11:40", "11:00&ndash;12:40")).lessons
    assert save(later, "en") == {"lang": "en", "was": 5, "had": ["ru", "kk"], "has": ["ru", "kk", "en"], "added": 0, "removed": 0, "moved": 1}
    assert mine()[0] == (1, "11:00", "Physical Education", "Gym", named("Physical Education", "ru", "kk", "en"))
    # the same language again: nothing changed; then Algebra gone, the Saturday class in another room, a new one
    assert did(save(later, "en")) == (0, 0, 0)
    edited = [dataclasses.replace(x, room="403") if x.subject == "Unlabelled Short Course" else x for x in later if x.subject != "Imaginary Algebra"]
    got = save([*edited, portal.Lesson(5, "09:00", "10:00", "Brand New Course", "practice", "101", None)], "en")
    assert did(got) == (1, 1, 1) and got["had"] == got["has"] == ["ru", "kk", "en"]
    now = {x[2]: x for x in mine()}
    assert "Imaginary Algebra" not in now and now["Brand New Course"][4] == {"en": "Brand New Course"}        # a new class: its page's name alone
    assert now["Unlabelled Short Course"][3:] == ("403", named("Unlabelled Short Course", "ru", "kk", "en"))
    # Kazakh again: Algebra back with its Kazakh name alone (it was gone), the new class goes, PE and the room back
    got = save(week["kk"].lessons, "kk")
    assert got == {"lang": "kk", "was": 5, "had": ["ru", "kk", "en"], "has": ["ru", "kk", "en"], "added": 1, "removed": 1, "moved": 2}
    assert [x[4] for x in mine()][:2] == [named("Physical Education", "ru", "kk", "en"), named("Imaginary Algebra", "kk")]
    # in a language they have, two classes that swapped times and rooms keep each its own names
    ru = {x.subject: x for x in week["ru"].lessons}
    h, lo = ru["History of Made-Up Things (ru)"], ru["Unlabelled Long Course (ru)"]
    swapped = [dataclasses.replace(h, begins=lo.begins, ends=lo.ends, room=lo.room), dataclasses.replace(lo, begins=h.begins, ends=h.ends, room=h.room)]
    got = save([x for x in week["ru"].lessons if x not in (h, lo)] + swapped, "ru")
    assert did(got) == (0, 0, 2)
    now = {x[2]: x for x in mine()}
    assert now["History of Made-Up Things (ru)"][1:4:2] == ("15:00", "305") and now["Unlabelled Long Course (ru)"][1] == "12:00"
    assert now["History of Made-Up Things (ru)"][4] == named("History of Made-Up Things", "ru", "kk", "en")
    assert now["Imaginary Algebra (ru)"][4] == named("Imaginary Algebra", "ru", "kk")                       # found again by its place
    assert mine(61) == [(1, "09:00", "Calculus", "305", {"en": "Calculus"})]                                # another student's: untouched

    # a week the bot saved before it kept languages (names NULL): its language from its letters, to show and to match by,
    # never written (a wrong guess would stick); a page in another language then carries only its own
    with db.tx(con):
        con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (bek["id"],))
        con.executemany("INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, kind, room, teacher) VALUES (?, 2, ?, ?, ?, 'lecture', '305', ?)",
                        [(bek["id"], "09:00", "10:50", phys, "Ivanov I."), (bek["id"], "11:00", "12:50", alg, "Ivanov I.")])
    assert [x[4] for x in mine(61)] == [{"ru": phys}, {"ru": alg}]
    assert did(save([portal.Lesson(2, "09:00", "10:50", phys, "lecture", "305", "Ivanov I.")], "ru", bek["id"])) == (0, 1, 0)  # by its name
    assert con.execute("SELECT names FROM schedule_classes WHERE user_id = ?", (bek["id"],)).fetchone()[0] == json.dumps({"ru": phys}, ensure_ascii=False)
    with db.tx(con):
        con.execute("UPDATE schedule_classes SET names = NULL WHERE user_id = ?", (bek["id"],))
    got = save([portal.Lesson(2, "09:00", "10:50", "Fizika (kk)", "lecture", "305", "\u0418\u0432\u0430\u043d\u043e\u0432 \u0418.")], "kk", bek["id"])
    assert (got["had"], got["has"], did(got)) == (["ru"], ["kk"], (0, 0, 0)) and [x[4] for x in mine(61)] == [{"kk": "Fizika (kk)"}]
    assert len(mine()) == 5


def test_schedule_merge_safety(env):
    """What keeps one course's names off another (the adversarial review, Oct 30). A page in a language a saved class
    has finds it by its name; in a new language by its place and its teacher (Latin or Cyrillic alike), never without
    one, and never where it could go two ways. Each saved class is taken once. Weeks as students' change: a course
    dropped and another in its slot, a new semester, two swapping days, two labs at one time."""
    from kbtu import portal
    c, cfg = env
    me = login(c, 70, "dana")
    con = db.connect(cfg.db_path)
    L = portal.Lesson
    cyr = {"Ivanov I.": "\u0418\u0432\u0430\u043d\u043e\u0432 \u0418.", "Petrov P.": "\u041f\u0435\u0442\u0440\u043e\u0432 \u041f.",
           "Akhmetov A.": "\u0410\u0445\u043c\u0435\u0442\u043e\u0432 \u0410."}  # how the Russian page writes them
    def ru(x):  # a class as the Russian page shows it
        return dataclasses.replace(x, subject=x.subject + " (ru)", teacher=cyr.get(x.teacher, x.teacher))
    def week(*pages):  # a fresh week, then each (lessons, language) in turn: what the last did, the names by (day, start)
        with db.tx(con):
            con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (me["id"],))
            for lessons, lang in pages:
                got = logic.save_schedule(con, me["id"], lessons, lang)
        return got, {(x["weekday"], x["begins"]): x["names"] for x in c.get("/api/me/schedule", headers=tma(70)).json()}
    def did(got):
        return got["added"], got["removed"], got["moved"]
    calc, phys = L(1, "09:00", "10:50", "Calculus", "lecture", "305", "Ivanov I."), L(2, "11:00", "11:50", "Physics", "practice", "410", "Petrov P.")

    # a new language: the same place and teacher (written in Cyrillic now) carries the names; Akhmetov too
    akh = L(3, "13:00", "13:50", "Algebra", "practice", "212", "Akhmetov A.")
    got, names = week(([calc, phys, akh], "en"), ([ru(calc), ru(phys), ru(akh)], "ru"))
    assert did(got) == (0, 0, 0) and names[(3, "13:00")] == {"en": "Algebra", "ru": "Algebra (ru)"}
    # S1 add/drop: Calculus dropped, Linear Algebra in its slot and hall (another teacher): no Calculus on it
    got, names = week(([calc, phys], "en"), ([ru(L(1, "09:00", "10:50", "Linear Algebra", "lecture", "305", "Serikova S.")), ru(phys)], "ru"))
    assert did(got) == (1, 1, 0) and names == {(1, "09:00"): {"ru": "Linear Algebra (ru)"}, (2, "11:00"): {"en": "Physics", "ru": "Physics (ru)"}}
    # S2 same day and room, later: Physics dropped, Chemistry added
    got, names = week(([phys], "en"), ([ru(L(2, "15:00", "15:50", "Chemistry", "practice", "410", "Bekova B."))], "ru"))
    assert did(got) == (1, 1, 0) and names == {(2, "15:00"): {"ru": "Chemistry (ru)"}}
    # S3 a new semester in a language the old week lacks: last term's names on none of it
    got, names = week(([calc, phys], "en"), ([ru(L(1, "09:00", "10:50", "Databases", "lecture", "305", "Omarov O.")),
                                             ru(L(2, "11:00", "11:50", "English B2", "practice", "410", "Lee L."))], "ru"))
    assert did(got) == (2, 2, 0) and all(set(n) == {"ru"} for n in names.values())
    # S4 two courses swap days in one hall at the same hours: neither takes the other's names
    phys3 = L(3, "09:00", "10:50", "Physics", "lecture", "305", "Petrov P.")
    got, names = week(([calc, phys3], "en"), ([ru(dataclasses.replace(phys3, weekday=1)), ru(dataclasses.replace(calc, weekday=3))], "ru"))
    assert all(set(n) == {"ru"} for n in names.values())
    # S5 two labs at one time in one room, both still there, the page's order reversed: each its own names
    odd, even = L(2, "12:00", "12:50", "Lab Odd Weeks", "lab", "505", "Abenov A."), L(2, "12:00", "12:50", "Lab Even Weeks", "lab", "505", "Bekova B.")
    got, _ = week(([odd, even], "en"), ([ru(even), ru(odd)], "ru"))
    rows_ = {x["subject"]: x["names"] for x in c.get("/api/me/schedule", headers=tma(70)).json()}
    assert did(got) == (0, 0, 0) and rows_["Lab Odd Weeks (ru)"] == {"en": "Lab Odd Weeks", "ru": "Lab Odd Weeks (ru)"}
    # by place, two ways pair none: one teacher's two classes at one time, one gone; one class as near to two
    got, names = week(([odd, dataclasses.replace(even, teacher="Abenov A.")], "en"), ([ru(odd)], "ru"))
    assert did(got) == (1, 2, 0) and names == {(2, "12:00"): {"ru": "Lab Odd Weeks (ru)"}}
    x9, y13 = L(1, "09:00", "09:50", "X", "practice", "403", "Ivanov I."), L(1, "13:00", "13:50", "Y", "practice", "403", "Ivanov I.")
    got, names = week(([x9, y13], "en"), ([ru(dataclasses.replace(y13, begins="11:00", ends="11:50"))], "ru"))
    assert names == {(1, "11:00"): {"ru": "Y (ru)"}}
    # ... even one clearly nearer: two of one teacher's in one room on one day pair none (the review, Oct 30)
    got, names = week(([x9, dataclasses.replace(y13, begins="15:00", ends="15:50")], "en"), ([ru(dataclasses.replace(y13, begins="16:00", ends="16:50"))], "ru"))
    assert did(got) == (1, 2, 0) and names == {(1, "16:00"): {"ru": "Y (ru)"}}
    # one alone there with its teacher, at another time: pairs
    got, names = week(([y13], "en"), ([ru(dataclasses.replace(y13, begins="16:00", ends="16:50"))], "ru"))
    assert did(got) == (0, 0, 1) and names == {(1, "16:00"): {"en": "Y", "ru": "Y (ru)"}}
    # course A swapped for B, one teacher, room and day, X staying: B doesn't take A's names
    b15 = dataclasses.replace(y13, subject="B", begins="15:00", ends="15:50")
    got, names = week(([x9, y13], "en"), ([ru(x9), ru(b15)], "ru"))
    assert did(got) == (1, 1, 0) and names == {(1, "09:00"): {"en": "X", "ru": "X (ru)"}, (1, "15:00"): {"ru": "B (ru)"}}
    # two at one time on both sides, both still there (one teacher, one room): neither takes the other's names
    got, names = week(([odd, dataclasses.replace(even, teacher="Abenov A.")], "en"), ([ru(dataclasses.replace(even, teacher="Abenov A.")), ru(odd)], "ru"))
    assert did(got) == (2, 2, 0) and all(set(n) == {"ru"} for n in names.values())
    # no teacher on either side: never by place
    got, names = week(([dataclasses.replace(calc, teacher=None)], "en"), ([ru(dataclasses.replace(calc, teacher=None))], "ru"))
    assert names == {(1, "09:00"): {"ru": "Calculus (ru)"}}

    # in a language the saved class has, by place never: X dropped and Y in its slot with the same teacher stays Y alone
    got, names = week(([x9], "en"), ([ru(x9)], "ru"), ([ru(dataclasses.replace(x9, subject="Y"))], "ru"))
    assert did(got) == (1, 1, 0) and names == {(1, "09:00"): {"ru": "Y (ru)"}}
    # a saved class is taken once: a second X on Monday is a new class, not the first one moved
    got, _ = week(([x9], "en"), ([x9, dataclasses.replace(x9, begins="11:00", ends="11:50")], "en"))
    assert did(got) == (1, 0, 0)
    # by name to another day: the names come along
    got, names = week(([x9], "en"), ([ru(x9)], "ru"), ([ru(dataclasses.replace(x9, weekday=4))], "ru"))
    assert did(got) == (0, 0, 1) and names == {(4, "09:00"): {"en": "X", "ru": "X (ru)"}}
    # by name within its day first, though another day's class is fewer minutes away
    late = dataclasses.replace(x9, begins="20:00", ends="20:50")
    got, names = week(([late], "en"), ([ru(late)], "ru"), ([ru(x9), ru(dataclasses.replace(x9, weekday=2, begins="06:00", ends="06:50"))], "ru"))
    assert did(got) == (1, 0, 1) and names == {(1, "09:00"): {"en": "X", "ru": "X (ru)"}, (2, "06:00"): {"ru": "X (ru)"}}
    # too many ways to weigh (a made-up week): by place none, by name in order
    tens = [dataclasses.replace(x9, begins=f"{8 + i:02d}:00", ends=f"{8 + i:02d}:50") for i in range(10)]
    fives = [dataclasses.replace(x9, begins=f"{8 + 2 * i:02d}:30", ends=f"{9 + 2 * i:02d}:10") for i in range(5)]
    got, names = week((tens, "en"), ([ru(x) for x in fives], "ru"))
    assert did(got) == (5, 10, 0) and all(set(n) == {"ru"} for n in names.values())
    assert did(week((tens, "en"), (fives, "en"))[0]) == (0, 5, 5)


def test_schedule_page_limits():
    """A made-up page can't stop or stall the bot (the review, Oct 30): too deep, too many tags or texts, too many
    classes: "not a schedule" at once; a stray end tag costs the same however deep the page is (it walked the whole
    open stack: quadratic)."""
    from kbtu import portal
    for page, why in (("<html><body>" + "<div>" * 5000 + "</body></html>", "deep"),
                      ("<html><body>" + "<div></div>" * 60_000 + "</body></html>", "big"),
                      ("<html><body>" + "<!-- -->" * 120_000 + "</body></html>", "big"),
                      ("<html><body>" + "<div>" * 190 + "x" * 1_000_001 + "</body></html>", "big")):  # words read 190 times
        with pytest.raises(portal.NotSchedule, match=why):
            portal.parse(page)
    start = time.perf_counter()  # an .mht of empty parts: refused before email's parser (minutes, GBs)
    with pytest.raises(portal.NotSchedule, match="big"):
        portal.page_html(b"MIME-Version: 1.0\nContent-Type: multipart/related; boundary=b\n\n" + b"--b\n\n\n" * 300_000 + b"--b--\n")
    assert time.perf_counter() - start < 1
    fixture = portal_page()
    block = re.search(r'<div class="absolute rounded-sm[^>]*top: 384px.*?</div>\s*</div>', fixture, re.S)[0]
    assert len(portal.parse(fixture.replace(block, block * 116)).lessons) == 120         # the most a week may have
    with pytest.raises(portal.NotSchedule, match="many"):
        portal.parse(fixture.replace(block, block * 117))
    t = portal._Tree()
    t.feed("<div><span><b>")
    t.feed("</p></i>")                                    # stray: nothing closes
    assert (t.at.tag, t.depth) == ("b", 3)
    t.feed("</div>")                                      # its element and what was left open inside it
    assert (t.at.tag, t.depth, sum(t.open.values())) == ("#root", 0, 0)

    def took(depth):
        page, best = "<html><body>" + "<div>" * depth + "</p>" * 30_000 + "</body></html>", 9e9
        for _ in range(3):
            start = time.perf_counter()
            with pytest.raises(portal.NotSchedule):
                portal.parse(page)
            best = min(best, time.perf_counter() - start)
        return best
    assert took(190) < 3 * took(1)                        # was 10x slower 190 deep


def test_schedule_bot_safety(env, monkeypatch):
    """One page that breaks the parser never stops the bot for everyone (the review, Oct 30: the batch was retried
    forever): the student hears "couldn't read the file", the others in the batch are answered once, the offset moves
    on. An account deleted while its page was read doesn't get its week back."""
    import httpx
    from kbtu import portal
    c, cfg = env
    login(c, 50, "ali")
    con = db.connect(cfg.db_path)
    page, real = portal_page(), portal.parse
    sent, t = [], logic.now()
    batch = [{"update_id": 7, "message": {"message_id": 1, "chat": {"id": 60, "type": "private"}, "from": {"id": 60}, "date": t, "text": "hi"}},
             {"update_id": 8, "message": {"message_id": 2, "chat": {"id": 50, "type": "private"}, "from": {"id": 50}, "date": t,
                                          "document": {"file_id": "F", "file_name": "Schedule.html", "file_size": 9}}}]

    def telegram(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [u for u in batch if u["update_id"] >= int(request.url.params["offset"])]})
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "F"}})
        if "/file/" in request.url.path:
            return httpx.Response(200, content=page.encode())
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def hear(offset):
        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as http:
            return await bot.hear(cfg, http, offset)
    def broken(html):
        raise RecursionError("maximum recursion depth exceeded")
    monkeypatch.setattr(portal, "parse", broken)
    assert asyncio.run(hear(0)) == 9 and [m["chat_id"] for m in sent] == [60, 50]
    assert sent[1]["text"] == texts.bot_message("ru", "sched_bad")[0]
    sent.clear()
    assert asyncio.run(hear(9)) == 9 and sent == []                                   # nothing again: the batch is done
    real_one = bot.one
    def locked(con_, sql, *a):  # the database locked in the ban check: that update skipped, the offset moves on
        if "banned_at" in sql:
            raise sqlite3.OperationalError("database is locked")
        return real_one(con_, sql, *a)
    monkeypatch.setattr(bot, "one", locked)
    assert asyncio.run(hear(0)) == 9
    monkeypatch.setattr(bot, "one", real_one)
    sent.clear()

    def meanwhile(html):  # the student deletes the account while the bot reads the page
        week = real(html)
        logic.delete_me(db.connect(cfg.db_path), logic.Viewer(con.execute("SELECT id FROM users WHERE tg_id = 50").fetchone()[0], "user", True))
        return week
    monkeypatch.setattr(portal, "parse", meanwhile)
    batch[:] = [{**batch[1], "update_id": 10}]
    assert asyncio.run(hear(10)) == 11 and sent[-1]["text"] == texts.bot_message("ru", "sched_signin")[0]
    assert con.execute("SELECT count(*) FROM schedule_classes s JOIN users u ON u.id = s.user_id WHERE u.tg_id = 50").fetchone()[0] == 0


def test_schedule_match_unlocked(env, monkeypatch):
    """The matcher runs outside the write lock (the review, Oct 30: 17 s held), the rows go in one short transaction
    that checks the student is still there and their week is still the one matched against."""
    from kbtu import portal
    from kbtu.logic import account
    c, cfg = env
    me = login(c, 71, "dana")
    con, other = db.connect(cfg.db_path), db.connect(cfg.db_path)
    x9 = portal.Lesson(1, "09:00", "09:50", "X", "practice", "403", "Ivanov I.")
    real, seen = account._merge, []

    def merge(saved, lessons, lang):  # while it matches, another writer gets the lock at once
        seen.append(con.in_transaction)
        if len(seen) == 1:  # another page lands meanwhile: matched again against it, under the lock this time
            with db.tx(other):
                other.execute("UPDATE schedule_classes SET names = '{\"en\": \"Calculus\"}' WHERE user_id = ?", (me["id"],))
        return real(saved, lessons, lang)
    monkeypatch.setattr(account, "_merge", merge)
    assert logic.save_schedule(con, me["id"], [x9], "en")["removed"] == 1 and seen == [False, True]
    assert logic.save_schedule(con, me["id"], [x9], "en")["removed"] == 0
    monkeypatch.setattr(account, "_merge", lambda *a: (logic.delete_me(other, logic.Viewer(me["id"], "user", True)), real(*a))[1])
    assert logic.save_schedule(con, me["id"], [x9], "en") is None                    # gone meanwhile: nothing written
    assert con.execute("SELECT count(*) FROM schedule_classes WHERE user_id = ?", (me["id"],)).fetchone()[0] == 0


def test_no_sunday_classes(env):
    c, cfg = env
    me = login(c, 80, "sun")
    con = db.connect(cfg.db_path)
    L = lambda d, t, s: types.SimpleNamespace(weekday=d, begins=t, ends="10:50", subject=s, code=None, kind="lecture", room="1", teacher=None)  # noqa: E731
    with db.tx(con):
        logic.save_schedule(con, me["id"], [L(1, "09:00", "Mon"), L(7, "09:00", "Sun")])  # an import drops Sunday
    assert [x["subject"] for x in c.get("/api/me/schedule", headers=tma(80)).json()] == ["Mon"]  # the old ones: migration 141
    assert not con.execute("SELECT 1 FROM schedule_classes WHERE subject = 'Sun'").fetchall()
    con.close()
