"""The student roster: name matching, freshmen prefill, identity fixes, claim links."""
from __future__ import annotations

import json
import re
import time

import pytest

from kbtu import auth, bot, config, db, logic
from test_core import BOT, delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def _ach_codes(person: dict) -> dict:
    """A profile's achievements by code, level; a badge's variants by their own code, 1 if held."""
    a = person["awards"]["achievements"]
    return {x["code"]: x["level"] for x in a} | {v["code"]: int(v["have"]) for x in a for v in x.get("variants", [])}


def test_roster_name_match():
    """PLAN 95's name check (made-up names): two words shared in any order and spelling, Cyrillic or Latin, Kazakh
    letters, a patronymic more; one shared word isn't enough."""
    from kbtu import roster
    erlan, nurlan = "\u0415\u0440\u043b\u0430\u043d", "\u041d\u0443\u0440\u043b\u0430\u043d\u043e\u0432"   # Yerlan Nurlanov in Russian
    assert roster.same_person("Nurlanov Yerlan Serikovich", erlan, nurlan)
    assert roster.same_person("Zhanna Ospanova", "Janna", "OSPANOVA") and roster.same_person("Akhmetov Daniyar", "Daniar", "Ahmetov")
    assert roster.same_person("\u049a\u0430\u0441\u044b\u043c \u0410\u043b\u0438", "Kasym", "Ali")                  # Kazakh Q
    assert not roster.same_person("Ivanov Petr", "Pavel", "Ivanov") and not roster.same_person(None, "A", "B")
    assert [roster.classify(p) for p in ("member", "President", "Vice president", "Head of SMM", "HR", "ex president")] == [
        ("member", None, None), ("president", None, None), ("vice", None, None), ("head", "Head of SMM", "SMM"), ("member", "HR", None),
        ("member", "ex president", None)]
    assert (roster.course_of("23BD", 2026), roster.course_of("3rd year"), roster.tg_of("@Some_User"), roster.tg_of("+77001234567")) == (4, 3, "some_user", None)


def test_roster_load_and_join(env):
    """PLAN 95 with made-up rows: the load is idempotent and makes missing clubs official; a student already in the app
    whose university email and name match joins at once (role, position as the club role's name, department, city, year,
    phone) with a toast once; listed but not signed in with Microsoft: a welcome with the club and position only; the
    username but another name: asked without the phone or city; "Yes, it's me" requests approval, the claim
    goes to the President, who confirms; the row's city and phone never come with a claim."""
    from kbtu import roster
    c, cfg = env
    pres = login(c, 70, "pres")
    ali = login(c, 71, "ali")          # Ali Testov (login()'s made-up students)
    bek = login(c, 72, "bek")
    guest = c.get("/api/me", headers=tma(73, "Guest")).json()
    con = db.connect(cfg.db_path)
    U = {71: "Ali_T", 72: "bek_t", 73: "new_one"}   # their Telegram usernames, as Telegram signs them
    h = lambda uid: {"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": "X", "username": U[uid]}, BOT)}  # noqa: E731
    for uid in U:
        c.get("/api/me", headers=h(uid))
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    row = lambda **k: {"sheet": "Open Mic sheet", "position": None, "title": None, "role": "member", "dept": None, "full_name": None, "school": "SITE",  # noqa: E731
                       "year": "2", "course": 2, "city": None, "phone": None, "tg": None, "email": None, **k}
    con.execute("UPDATE students SET email = 'ali@kbtu.kz' WHERE user_id = ?", (ali["id"],))
    items = [row(full_name="Testov Ali Made", email="ali@kbtu.kz", tg="ali_t", position="Head of SMM", title="Head of SMM", role="head", dept="SMM", city="Taraz", phone="8 701 000 00 00"),
             row(full_name="Someone Else", tg="bek_t", position="Head of HR", title="Head of HR", role="head", city="Aktau", phone="+77010000001"),
             row(full_name="Not Yet Here", tg="new_one", position="Vice president", role="vice", city="Shymkent"),
             {**row(full_name="New Club Person", tg="nobody_here"), "sheet": "Chess sheet"}]
    orgmap = {"Open Mic sheet": "mic", "Chess sheet": {"new": {"name": "Chess Club KBTU", "short": "CC", "emoji": "game_die_3d"}}}
    got = roster.load(con, items, orgmap)
    assert (got["added"], got["orgs_made"], got["joined"]) == (4, ["Chess Club KBTU"], 1)
    assert roster.load(con, items, orgmap)["added"] == 0                                   # again: nothing new
    assert con.execute("SELECT official FROM orgs WHERE name = 'Chess'").fetchone()[0] == 1          # no "KBTU" in a name

    me = c.get("/api/me", headers=h(71)).json()                                         # Ali: joined, told once
    assert [(m["org"]["slug"], m["role"], m["title"]) for m in me["memberships"]] == [("mic", "head", "Head of SMM")]
    assert me["roster"]["joined"][0]["title"] == "Head of SMM" and me["city"] == {"name": "Taraz", "hidden": False} and me["student"]["phone"] == "+77010000000"
    assert c.post("/api/roster/seen", headers=h(71)).status_code == 204 and c.get("/api/me", headers=h(71)).json()["roster"] is None
    assert con.execute("""SELECT g.name FROM member_tags t JOIN org_tags g ON g.id = t.tag_id WHERE t.user_id = ? AND g.department = 1""", (ali["id"],)).fetchone()[0] == "SMM"
    assert c.get(f"/api/users/{ali['id']}", headers=tma(70)).json()["city"] == "Taraz"
    c.patch("/api/me", headers=h(71), json={"cityHidden": True})
    assert c.get(f"/api/users/{ali['id']}", headers=tma(70)).json()["city"] is None
    assert c.patch("/api/me", headers=h(71), json={"city": None}).json()["city"] is None   # deleted
    assert c.patch("/api/me", headers=h(71), json={"city": "  \u0422\u0430\u0440\u0430\u0437 "}).json()["city"]["name"] == "\u0422\u0430\u0440\u0430\u0437"  # mine to set (Nov 3)
    for bad in ("", "x", "<b>", "http://a.kz", "1234", 5, "a" * 41):
        assert c.patch("/api/me", headers=h(71), json={"city": bad}).status_code == 400, bad

    welcome = c.get("/api/me", headers=h(73)).json()["roster"]                         # not signed in with Microsoft
    assert welcome == {"welcome": [{"org": welcome["welcome"][0]["org"], "title": None, "role": "vice"}]} and welcome["welcome"][0]["org"]["slug"] == "mic"

    me = c.get("/api/me", headers=h(72)).json()  # A handle alone requires the President's confirmation.
    assert not me["memberships"] and me["city"] is None
    assert roster.asks(con, bek["id"]) and not con.execute("SELECT phone FROM students WHERE user_id = ?", (bek["id"],)).fetchone()[0]


def test_roster_app_wins(env):
    """PLAN 95, students already in the app: what the app has wins. A membership held keeps its role (no
    promotion, no demotion); a missing one is added, a President on the sheet where the club has another in the app
    comes in as Vice (counted in the load's summary); department, title, city, phone and year fill only what's empty."""
    from kbtu import roster
    c, cfg = env
    pres, ali, bek = login(c, 60, "pres"), login(c, 61, "ali"), login(c, 62, "bek")
    con = db.connect(cfg.db_path)
    for uid, name in ((61, "ali_u"), (62, "bek_u")):
        c.get("/api/me", headers={"Authorization": "tma " + auth.sign_init_data({"id": uid, "first_name": "X", "username": name}, BOT)})
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, ?, 0)", [(pres["id"], "president"), (ali["id"], "vice")])
    con.execute("UPDATE users SET city = 'Almaty' WHERE id = ?", (ali["id"],))
    con.execute("UPDATE students SET phone = '+77010000009', course = 3 WHERE user_id = ?", (ali["id"],))
    row = lambda **k: {"sheet": "S", "position": "President", "title": None, "role": "president", "dept": None, "school": None, "year": "1",  # noqa: E731
                       "course": 1, "city": "Taraz", "phone": "+77010000001", "email": None, **k}
    con.execute("UPDATE students SET email = lower(first_name) || '@kbtu.kz'")
    got = roster.load(con, [row(full_name="Ali Testov", email="ali@kbtu.kz", tg="ali_u", dept="Board"), row(full_name="Bek Testov", email="bek@kbtu.kz", tg="bek_u")], {"S": "mic"})
    assert (got["joined"], got["president_as_vice"]) == (2, 1)
    roles = dict(con.execute("SELECT user_id, role FROM org_members WHERE org_id = 1").fetchall())
    assert roles == {pres["id"]: "president", ali["id"]: "vice", bek["id"]: "vice"}            # one President: the app's
    a = con.execute("SELECT u.city, s.phone, s.course FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ?", (ali["id"],)).fetchone()
    assert tuple(a) == ("Almaty", "+77010000009", 3)                                           # ours stayed
    b = con.execute("SELECT u.city, s.phone FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = ?", (bek["id"],)).fetchone()
    assert tuple(b) == ("Taraz", "+77010000001")                                               # empty ones filled
    assert con.execute("SELECT g.name FROM member_tags t JOIN org_tags g ON g.id = t.tag_id WHERE t.user_id = ?", (ali["id"],)).fetchone()[0] == "Board"


def test_freshmen_prefill(env, monkeypatch, capsys):
    """The Oct 31 2026 initiation's freshmen list (admin prefill-import, made-up people): IDs normalised, bad and doubled
    rows dropped, counts printed and never a value, each list once; a student already confirmed with the row's ID who
    came gets the badge at once; only the student whose KBTU mail it is sees it, in their own form, with names only where
    Microsoft has none; linking with the row's ID fills what their row lacks and gives "came" its badge, with another ID
    nothing; the row goes either way; never an ID another student holds; deleting an account takes its row along."""
    import io
    from kbtu import admin, checkin
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    login(c, 1, "held")
    came = login(c, 5, "came")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (came["id"],))  # the owner hears of mismatches
    con.execute("UPDATE students SET student_id = '25B000009', email = 'held@kbtu.kz', ms_oid = 'oid-held' WHERE student_id = '24Bheld'")
    con.execute("UPDATE students SET student_id = '25B000005', email = 'came@kbtu.kz', ms_oid = 'oid-came' WHERE student_id = '24Bcame'")
    lines = ["email,student_id,last,first,middle,school,phone,came",
             "A_One@kbtu.kz, 25\u0432 01 0001 ,\u041e\u0441\u043f\u0430\u043d\u043e\u0432\u0430,\u0410\u0439\u0430,Sultanqyzy,SITE,8 701 000 00 01,1",   # Cyrillic Ve, spaces, upper mail
             "b_two@kbtu.kz,25\u0418O10002,Twoev,Bek,,ISE,+7 701 000 00 02,0",                   # Cyrillic I; an O for a zero
             "b_two@kbtu.kz,25B010002,Twoev,Bek,,ISE,,1",                                        # the same again: one row, came
             "c_three@kbtu.kz,25B010003,,,,,,1",
             "c_three@kbtu.kz,25B010033,,,,,,1",                                                 # one mail, two IDs
             "d_four@kbtu.kz,25B010004,,,,,,0",
             "e_five@kbtu.kz,25B010004,,,,,,0",                                                  # one ID, two mails
             "f_six@gmail.com,25B010006,,,,,,0",                                                 # not a KBTU mail
             ",25B010007,,,,,,0",
             "g_seven@kbtu.kz,hello,,,,,,0",
             "h_eight@kbtu.kz,99B010008,,,,,,0",                                                 # a year ahead
             "held@kbtu.kz,25B010010,,,,,,1",                                                    # signed up already, another ID
             "came@kbtu.kz,25B000005,Testov,Came,,,,1",                                          # signed up already, came: badged
             "i_nine@kbtu.kz,25B000009,,,,,,1",                                                  # another student's ID
             "j_ten@kbtu.kz,26B010010,\u0422\u0435\u043d,\u0416\u0430\u043d,,,77010000001.0,0"]                                      # this intake; an Excel phone

    def run(text: str, name: str) -> str:
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(text.encode())))
        capsys.readouterr()
        admin.main(["prefill-import", "--list", name])
        return capsys.readouterr().out
    out = run("\n".join(lines) + "\n", "init26")
    assert out.split("\n")[0] == ("rows 15  kept 3  same 1  badged 1  bad_email 2  bad_id 2  dup_email 2  dup_id 2  signed_up 1  "
                                  "id_held 1  bad_phone 1")
    assert "kbtu.kz" not in out and "25B" not in out and "Aya" not in out                 # counts only
    assert [tuple(r) for r in con.execute("SELECT email, student_id, phone, came FROM prefill ORDER BY email")] == [
        ("a_one@kbtu.kz", "25B010001", "+77010000001", 1), ("b_two@kbtu.kz", "25B010002", "+77010000002", 1),
        ("j_ten@kbtu.kz", "26B010010", None, 0)]
    ach = lambda uid: _ach_codes(c.get(f"/api/users/{uid}", headers=tma(1)).json())  # noqa: E731
    assert ach(came["id"])["init26f"] == 1
    with pytest.raises(SystemExit) as e:
        run("\n".join(lines) + "\n", "init26")                                             # each list once
    assert "once" in str(e.value)
    assert run("\n".join(lines) + "\n", "init26b").split("\n")[0].startswith("rows 15  kept 3  same 1  badged 0")
    with pytest.raises(SystemExit):
        run("email,student_id\nx@kbtu.kz,25B010001\n", "x1")                               # the wrong header: nothing
    with pytest.raises(SystemExit) as e:
        run(lines[0] + "\nx@kbtu.kz,25B010011,,,,,,yes\n", "x2")
    assert "line 2" in str(e.value) and "x@" not in str(e.value)
    assert [logic.account.norm_sid(x) for x in ("25b010001", "25\u041c010001", "2\u041e\u0412010", "25X12")] \
        == ["25B010001", "25M010001", None, None]
    # only the student Microsoft vouches for sees it, and only when the name matches too (Latin vs Cyrillic)
    who = lambda tg, mail, first, last: {"oid": f"oid-{tg}", "email": mail, "first": first, "last": last, "employeeId": "", "profile": {}}  # noqa: E731
    uid = {tg: c.get("/api/me", headers=tma(tg)).json()["id"] for tg in (2, 3, 4, 6, 7)}
    logic.ms_remember(con, uid[2], who(2, "a_one@kbtu.kz", "Aya", "Ospanova"))
    logic.ms_remember(con, uid[3], who(3, "z_typo@kbtu.kz", "Zed", "Other"))
    con.execute("INSERT INTO prefill (email, student_id, last_name, first_name, phone, came) VALUES ('z_typo@kbtu.kz', '25B010050', 'Serikov', 'Bolat', '+77010000099', 1)")
    assert c.get("/api/me", headers=tma(2)).json()["msPending"]["prefill"] == {"studentId": "25B010001"}
    assert c.get("/api/me", headers=tma(3)).json()["msPending"]["prefill"] is None          # another person's name: nothing
    assert c.get("/api/me", headers=tma(4)).json()["msPending"] is None
    # never an ID another student holds, from either list
    con.execute("INSERT INTO prefill (email, student_id, last_name, first_name, came) VALUES ('h_eld@kbtu.kz', '25B000009', 'Ten', 'Jan', 1)")
    assert checkin.prefill(con, "h_eld@kbtu.kz", {"first": "Jan", "last": "Ten"}) is None
    assert checkin.new(con, "Meeting", [{"email": "q_list@kbtu.kz", "name": "Q List", "studentId": "25B000009"}], None)
    assert checkin.prefill(con, "q_list@kbtu.kz") is None
    alerts = lambda: [tuple(r) for r in con.execute(  # noqa: E731
        "SELECT kind, ref FROM bot_outbox WHERE user_id = ? AND kind LIKE 'prefill_%' ORDER BY id", (came["id"],))]
    # linking with the row's ID and name: what the row lacks, the badge for "came", the row gone, nothing to check
    r = c.post("/api/kbtu/manual", headers=tma(2), json={"studentId": "25B010001", "consentVersion": logic.CONSENT})
    assert r.status_code == 200, r.text
    s = con.execute("SELECT middle_name, middle_lat, school, phone FROM students WHERE user_id = ?", (uid[2],)).fetchone()
    assert tuple(s) == (None, "Sultanqyzy", "SITE", "+77010000001")  # a Latin middle name: the Latin column
    assert not con.execute("SELECT 1 FROM prefill WHERE email = 'a_one@kbtu.kz'").fetchone()
    assert ach(uid[2])["init26f"] == 1 and ach(uid[2])["init26"] == 0 and alerts() == []
    out = con.execute("SELECT * FROM bot_outbox WHERE user_id = ? AND ref = 'ach:init26f:1'", (uid[2],)).fetchone()
    assert bot._render(con, {**dict(out), "lang": "kk"})                                    # the bot's card has its name
    # a typo'd mail, another person's name: nothing from the row, no badge, the row stays, no alert
    r = c.post("/api/kbtu/manual", headers=tma(3), json={"studentId": "25B010099", "consentVersion": logic.CONSENT})
    assert r.status_code == 200, r.text
    assert con.execute("SELECT phone FROM students WHERE user_id = ?", (uid[3],)).fetchone()[0] is None
    assert ach(uid[3])["init26f"] == 0 and con.execute("SELECT 1 FROM prefill WHERE email = 'z_typo@kbtu.kz'").fetchone()
    assert alerts() == []
    # the name matches but the row's ID is another student's: used, and the owner hears
    logic.ms_remember(con, uid[6], who(6, "h_eld@kbtu.kz", "Jan", "Ten"))
    assert c.post("/api/kbtu/manual", headers=tma(6), json={"studentId": "26B010011", "consentVersion": logic.CONSENT}).status_code == 200
    held = con.execute("SELECT user_id FROM students WHERE student_id = '25B000009'").fetchone()[0]
    assert ach(uid[6])["init26f"] == 1 and alerts() == [("prefill_id_held", f"ph:{uid[6]}:{held}")]
    # the name matches (Cyrillic list, Latin Microsoft) but the student gives another ID than the row's
    logic.ms_remember(con, uid[7], who(7, "j_ten@kbtu.kz", "Zhan", "Ten"))
    assert c.post("/api/kbtu/manual", headers=tma(7), json={"studentId": "26B010012", "consentVersion": logic.CONSENT}).status_code == 200
    assert alerts()[1:] == [("prefill_other_id", f"pf:{uid[7]}")]
    assert not con.execute("SELECT 1 FROM prefill WHERE email = 'j_ten@kbtu.kz'").fetchone()
    for kind, ref in alerts():
        out = con.execute("SELECT * FROM bot_outbox WHERE kind = ? AND ref = ?", (kind, ref)).fetchone()
        text = bot._render(con, {**dict(out), "lang": "en"})[0]
        assert f"#{ref.split(':')[1]}" in text and "kbtu.kz" not in text and "B0" not in text and "Serikov" not in text
    # deleting an account before it linked: its row goes too
    logic.ms_remember(con, uid[4], who(4, "b_two@kbtu.kz", "Bek", "Twoev"))
    logic.delete_me(con, logic.Viewer(uid[4], "user", False))
    assert not con.execute("SELECT 1 FROM prefill WHERE email = 'b_two@kbtu.kz'").fetchone()
    con.execute("INSERT INTO prefill (email, student_id) VALUES ('held@kbtu.kz', '25B010010')")   # a student's own mail
    delete_now(c, cfg, tma(1))
    assert [k for k, _ in alerts()] == ["prefill_other_id"]                                  # the alert naming them went too
    assert not con.execute("SELECT 1 FROM prefill WHERE email = 'held@kbtu.kz'").fetchone()
    con.close()


def test_same_person_kazakh_spellings():
    """Passport Latin vs the Cyrillic list: -ayev/-aev, -iyeva/-ieva, a hyphen, Kazakh letters, accents (review, Oct 31)."""
    from kbtu.roster import same_person
    assert same_person("\u0422\u043e\u043a\u0442\u0430\u0440\u0431\u0430\u0435\u0432 \u0415\u0440\u043b\u0430\u043d", "Yerlan", "Toktarbayev")
    assert same_person("\u0410\u0431\u0430\u0435\u0432\u0430 \u0410\u0439\u0433\u0435\u0440\u0438\u043c", "Aigerim", "Abayeva")
    assert same_person("\u0410\u043b\u0438\u0435\u0432\u0430 \u041c\u0430\u0440\u0438\u044f", "Mariya", "Aliyeva")
    assert same_person("\u0418\u0431\u0440\u0430\u0435\u0432 \u0410\u0440\u0443\u0436\u0430\u043d", "Aru-Zhan", "Ibrayev")
    assert same_person("\u041c\u0443\u0441\u0430\u0435\u0432 \u041d\u04b1\u0440\u0441\u04b1\u043b\u0442\u0430\u043d", "Nursultan", "Mussayev")
    assert same_person("\u0410\u0445\u043c\u0435\u0442\u043e\u0432\u0430 \u04d8\u0441\u0435\u043b", "\u00c4sel", "Akhmetova")
    assert not same_person("\u0418\u0432\u0430\u043d\u043e\u0432 \u0418\u0432\u0430\u043d", "Petr", "Sidorov")


def test_identity_earlier_intake(env):
    """26B typed for 25B (a student, Nov 2): an earlier intake year is hers to fix (it only loses 1st-year seats); the course follows."""
    c, cfg = env
    ali = login(c, 10, "ali")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET student_id = '26B031234', course = 1 WHERE user_id = ?", (ali["id"],))
    r = c.patch("/api/me", headers=tma(10), json={"studentId": "25B031234"})
    assert r.status_code == 200, r.text
    row = con.execute("SELECT student_id, course FROM students WHERE user_id = ?", (ali["id"],)).fetchone()
    assert row[0] == "25B031234" and row[1] >= 2
    con.close()


def test_identity_fix_once(env, monkeypatch):
    """Settings -> My data: the student ID and each name corrected once (review identity-edit-review.md); the ID within
    its intake year and free, first/last only as KBTU's own name in another spelling; the old value in the audit log;
    the admin's path has no once and no tolerance. A master's 4-digit ID is a valid one."""
    c, cfg = env
    ali, bek, staff = login(c, 10, "ali"), login(c, 11, "bek"), login(c, 12, "stf")
    con = db.connect(cfg.db_path)
    con.execute("""UPDATE students SET student_id = '26B031234', first_name = 'Aidos', last_name = 'Serikbayev', course = 3,
        ms_profile = '{"givenName": "Aidos", "surname": "Serikbayev"}' WHERE user_id = ?""", (ali["id"],))
    con.execute("UPDATE students SET student_id = '26B031235' WHERE user_id = ?", (bek["id"],))
    con.execute("UPDATE students SET consent_version = 'staff' WHERE user_id = ?", (staff["id"],))
    fix = lambda **b: c.patch("/api/me", headers=tma(10), json=b)  # noqa: E731
    con.execute("UPDATE students SET student_id = '25B031234' WHERE user_id = ?", (ali["id"],))
    assert fix(studentId="26B031236").json()["message"] == "sid_year"         # a later intake (a 1st-year's seats): support
    con.execute("UPDATE students SET student_id = '26B031234' WHERE user_id = ?", (ali["id"],))
    con.execute("INSERT INTO prefill (email, student_id) VALUES ('other@kbtu.kz', '26B031240')")
    assert fix(studentId="26B031240").json()["message"] == "sid_taken"       # kept for another mail by the freshmen list
    assert fix(studentId="26B\uff10\uff13\uff11\uff12\uff13\uff19").status_code == 400  # fullwidth digits: a clone of a real ID
    r = fix(studentId="26B031235")                                           # bek's: refused, not spent
    assert r.status_code == 409 and r.json()["message"] == "sid_taken"
    me = fix(studentId=" 26b 031237").json()["student"]
    assert me["studentId"] == "26B031237" and me["course"] == 3 and "studentId" not in me["fixable"]  # a typo: the course stays
    assert fix(studentId="26B031238").json()["message"] == "fixed"           # once
    assert fix(lastName="Kim").json()["message"] == "name_far"               # someone else's name: support
    assert fix(lastName="Serikbayev Rector").json()["message"] == "name_far"  # KBTU's words kept, one added
    assert fix(firstName="Aidos Bekzat").json()["message"] == "name_far"
    assert fix(firstName="Aidan").json()["message"] == "name_far"           # two letters off: another name
    surname = "\u0421\u0435\u0440\u0438\u043a\u0431\u0430\u0435\u0432"
    assert fix(lastName=surname).json()["student"]["lastName"] == surname    # KBTU's name in Cyrillic
    assert fix(middleName="").json()["student"]["fixable"] == ["firstName", "middleName", "lastLat", "firstLat", "middleLat", "course", "school"]  # nothing changed: not spent
    assert fix(middleName="Kairatuly").json()["student"]["middleName"] == "Kairatuly"
    assert fix(middleName="X").json()["message"] == "fixed"
    assert fix(email="x@kbtu.kz").json()["student"]["email"] == ali["student"]["email"]  # never: it's the Microsoft login
    log = [json.loads(d) for (d,) in con.execute("SELECT data FROM audit_log WHERE action = 'identity_fix' AND target = ? ORDER BY id", (f"user:{ali['id']}",))]
    assert [(x["field"], x["old"]) for x in log] == [("student_id", "26B031234"), ("last_name", "Serikbayev"), ("middle_name", None)]
    assert c.patch("/api/me", headers=tma(12), json={"middleName": "A"}).status_code == 403  # staff: a placeholder ID
    logic.fix_identity(con, ali["id"], "last_name", "Kim", admin=True)       # support: anything, any time
    logic.fix_identity(con, ali["id"], "student_id", "24MD1234", admin=True)
    s = con.execute("SELECT last_name, student_id, course, fixed FROM students WHERE user_id = ?", (ali["id"],)).fetchone()
    assert tuple(s) == ("Kim", "24MD1234", 2, "student_id,last_name,middle_name")
    assert logic.STUDENT_ID.fullmatch("26MD1234") and logic.account.norm_sid("26md1234") == "26MD1234"
    assert not logic.STUDENT_ID.fullmatch("25B0101") and logic.account.norm_sid("25B0101") is None  # a bachelor's: 5 digits at least
    from kbtu import admin
    monkeypatch.setattr(config, "load", lambda: cfg)
    admin.main(["fix", "10", "reset"])                                      # support gives the once back, logged
    assert con.execute("SELECT fixed FROM students WHERE user_id = ?", (ali["id"],)).fetchone()[0] == ""
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'identity_fix_reset' AND target = ?", (f"user:{ali['id']}",)).fetchone()[0] == 1


def test_once_edit(env, monkeypatch):
    """Review once-edit (Nov 2): an ID that makes a 1st-year bachelor is support's, any other year mine once; an ID on a
    check-in's expected list for another mail is taken (an absent friend shown as "came"); 5 ID tries a day, taken or
    not; a save is all or nothing, yet a taken try still counts and the admins still hear."""
    import calendar
    from kbtu import checkin
    c, cfg = env
    ali, bek, boss = login(c, 10, "ali"), login(c, 11, "bek"), login(c, 12, "boss")
    con = db.connect(cfg.db_path)
    t0 = calendar.timegm((2026, 10, 1, 0, 0, 0))
    set_clock(monkeypatch, lambda: t0)
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss["id"],))
    con.execute("UPDATE students SET student_id = '24B031234', course = 3, email = 'ali@kbtu.kz' WHERE user_id = ?", (ali["id"],))
    con.execute("UPDATE students SET student_id = '24B031235' WHERE user_id = ?", (bek["id"],))
    fix = lambda **b: c.patch("/api/me", headers=tma(10), json=b)  # noqa: E731
    row = lambda: con.execute("SELECT student_id, course, phone, school, fixed FROM students WHERE user_id = ?", (ali["id"],)).fetchone()  # noqa: E731
    again = lambda **k: con.execute(f"UPDATE students SET {''.join(f'{x} = ?, ' for x in k)}fixed = '' WHERE user_id = ?", (*k.values(), ali["id"]))  # noqa: E731
    r = fix(phone="+77011234567", studentId="24B031235")                     # bek's, with a phone in the same save
    assert r.json()["message"] == "sid_taken" and row()["phone"] is None    # all or nothing: the phone isn't saved
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'sid_check' AND user_id = ?", (bek["id"],)).fetchone()[0] == 1  # yet the holder is asked
    checkin.new(con, "Meeting", [{"email": "friend@kbtu.kz", "name": "Friend", "studentId": "24b099001"},
                                 {"email": "ali@kbtu.kz", "name": "Ali", "studentId": "24B099002"}])
    assert fix(studentId="24B099001").json()["message"] == "sid_taken"      # an absent friend's place on the list
    assert "studentId" in c.get("/api/me", headers=tma(10)).json()["student"]["fixable"]  # not spent
    assert fix(studentId="26B031234").json()["message"] == "sid_year"       # year 3 into year 1 (free seats): support
    assert tuple(row())[:2] == ("24B031234", 3)
    assert fix(studentId="25B031234").json()["student"]["course"] == 2      # a later year, still not the 1st: mine
    again(student_id="26M031234", course=1)
    assert fix(studentId="26B031234").json()["message"] == "sid_year"       # a 1st-year master into a bachelor: support
    again(student_id="26B031234", course=1)
    assert fix(studentId="26B031299").status_code == 200                    # a 1st-year's typo: theirs
    again()
    assert fix(studentId="24B099002").status_code == 200                    # on a list under my own mail: mine
    again()
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'sid_try' AND actor_id = ?", (ali["id"],)).fetchone()[0] == 2
    r = fix(studentId="24B031240")                                          # the 6th try today (2 taken, 3 saved)
    assert r.status_code == 429 and r.json()["message"] == "sid_tries"
    set_clock(monkeypatch, lambda: t0 + 86401)
    assert fix(studentId="24B031240").status_code == 200                    # tomorrow: again
    assert fix(school=None, course=9).status_code == 400 and row()["school"] == "SITE"  # a refused course keeps the school
    con.close()


def test_once_undo(env):
    """A school or course corrected by mistake goes back to what it was, free, once; then it stays (owner, Nov 3)."""
    c, cfg = env
    login(c, 30, "nur")
    con = db.connect(cfg.db_path)
    con.execute("""INSERT INTO orgs (slug, kind, name, short, emoji, official, created_at) VALUES ('site', 'school', 'SITE', 'IT', 'laptop_3d', 1, 0),
        ('sce', 'school', 'SCE', 'SC', 'laptop_3d', 1, 0), ('law', 'school', 'LAW', 'LA', 'laptop_3d', 1, 0)""")
    con.execute("UPDATE students SET school = 'SITE' WHERE user_id = (SELECT id FROM users WHERE tg_id = 30)")
    con.commit()
    me = lambda **b: c.patch("/api/me", headers=tma(30), json=b)  # noqa: E731
    r = me(school="SCE").json()["student"]                                   # the mis-tap: the once spent
    assert r["school"] == "SCE" and "school" not in r["fixable"] and r["undo"] == {"school": "SITE"}
    assert me(school="LAW").json()["message"] == "fixed"                     # not another one
    r = me(school="SITE").json()["student"]                                  # back to mine: free
    assert r["school"] == "SITE" and r["undo"] == {}
    assert me(school="SCE").json()["message"] == "fixed"                     # and no flipping back and forth
    con.execute("UPDATE students SET school = '\u0428\u0418\u0422\u0438\u0418', fixed = '', once_was = '{}' WHERE user_id = (SELECT id FROM users WHERE tg_id = 30)")
    con.commit()                                                             # as the portal wrote it, not an org's name
    assert me(school="SCE").json()["student"]["undo"] == {"school": "\u0428\u0418\u0422\u0438\u0418"}
    assert me(school="\u0428\u0418\u0422\u0438\u0418").json()["student"]["school"] == "\u0428\u0418\u0422\u0438\u0418"
    con.close()


def test_latin_names(env, monkeypatch, capsys):
    """The name in Latin (latin-names-review.md, made-up people): read from Microsoft's displayName word by word or a Latin
    freshmen-list row, never generated; a Latin list middle name never lands in the Cyrillic column; never over a value
    on a relink; My data takes Latin letters only, KBTU's name in another spelling, an empty one filled without spending
    the once; the English UI gets it through i18n; the admin's probe prints counts only, --apply fills the empty ones."""
    from kbtu import admin
    from kbtu.logic.account import latin_from_ms
    from kbtu.roster import same_person
    aidos, sur, mid = "\u0410\u0439\u0434\u043e\u0441", "\u0421\u0435\u0440\u0438\u043a\u0431\u0430\u0435\u0432", "\u041a\u0430\u0439\u0440\u0430\u0442\u0443\u043b\u044b"
    pr = lambda dn: {"displayName": dn, "givenName": aidos, "surname": sur}  # noqa: E731
    assert latin_from_ms(pr("Aidos Serikbayev"))[0] == {"first_lat": "Aidos", "last_lat": "Serikbayev", "middle_lat": None}
    assert latin_from_ms(pr("Serikbayev Aidos Kairatuly"), mid)[0]["middle_lat"] == "Kairatuly"
    assert latin_from_ms(pr("Serikbayev Aidos Kairatuly"))[0]["middle_lat"] is None          # no known middle: dropped
    for bad in ("s_serikbayev@kbtu.kz", f"{aidos} {sur}", "Serikbayev A.", "Aidos Serikbayev (Student)", "Aidos Serikbayev 23B",
                "Aidos Serikbayev Kairat Uly", "Aidos", ""):
        assert latin_from_ms(pr(bad))[0] is None, bad
    assert same_person("\u0429\u0443\u043a\u0438\u043d \u0418\u0432\u0430\u043d", "Ivan", "Shchukin")
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    uid, bek = login(c, 10, "ali")["id"], login(c, 11, "bek")["id"]
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET first_name = ?, last_name = ? WHERE user_id IN (?, ?)", (aidos, sur, uid, bek))
    con.execute("""INSERT INTO prefill (email, student_id, last_name, first_name, middle_name) VALUES
        ('ali@kbtu.kz', '24Bali', 'Serikbaev', 'Aidos', 'Kairatuly')""")
    who = lambda dn: {"oid": "oid-a", "email": "ali@kbtu.kz", "first": aidos, "last": sur, "profile": pr(dn)}  # noqa: E731
    lat = lambda u: tuple(con.execute("SELECT last_lat, first_lat, middle_lat, middle_name FROM students WHERE user_id = ?", (u,)).fetchone())  # noqa: E731
    logic.ms_link(con, uid, who("Aidos Serikbayev"))
    assert lat(uid) == ("Serikbayev", "Aidos", "Kairatuly", None)       # the directory over the list; its Latin middle: Latin
    logic.ms_link(con, uid, who("Serikbaev Aidos"))
    assert lat(uid)[0] == "Serikbayev"                                   # a relink never over a value
    fix = lambda **b: c.patch("/api/me", headers=tma(10), json=b)  # noqa: E731
    assert fix(lastLat=sur).json()["error"] == "bad_input"            # Latin letters only
    assert fix(lastLat="Kim").json()["message"] == "name_far"
    con.execute("UPDATE students SET middle_lat = NULL WHERE user_id = ?", (uid,))
    assert "middleLat" in fix(middleLat="Kairatovich").json()["student"]["fixable"]  # an empty one filled: not spent
    st = fix(lastLat="Serikbaiev").json()["student"]
    assert st["lastLat"] == "Serikbaiev" and "lastLat" not in st["fixable"]
    assert fix(lastLat="Serikbayev").json()["message"] == "fixed"
    ref = lambda: logic.person_ref(con.execute(logic.PERSON + " WHERE u.id = ?", (uid,)).fetchone())  # noqa: E731
    assert ref()["i18n"] == {"en": {"name": "Aidos S", "realName": "Aidos S"}} and c.get("/api/me", headers=tma(10)).json()["i18n"]["en"]["name"] == "Aidos S"
    con.execute("UPDATE users SET nick = 'Ace' WHERE id = ?", (uid,))
    assert ref()["i18n"] == {"en": {"realName": "Aidos S"}} and ref()["name"] == "Ace"  # a nick is the same in every language
    # the probe: counts only; --apply fills the empty columns of those linked before, once
    con.execute("UPDATE students SET ms_profile = ? WHERE user_id = ?", (json.dumps(pr("Aidos Serikbayev")), bek))
    capsys.readouterr()
    admin.main(["latin-names"])
    out = capsys.readouterr().out
    assert "parse_ok" in out and "nothing written" in out and "Aidos" not in out and "Serik" not in out and lat(bek)[0] is None
    admin.main(["latin-names", "--apply"])
    admin.main(["latin-names", "--apply"])
    assert lat(bek) == ("Serikbayev", "Aidos", None, None)
    con.close()


def test_prefill_rest(env, monkeypatch, capsys):
    """The rest of the freshmen list (prefill-rest-and-claim-review.md A, made-up people): rows the main import didn't keep;
    a confirmed student with the row's mail or ID and name is badged now; the others wait (a shared ID matches by nothing,
    the raw ID kept for the owner only) and give their student the badge and what their row lacks at sign-in, never the
    ID; rows kept once and gone since never come back; deleting an account takes its rows, not a namesake's by ID."""
    import io
    from kbtu import admin
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    came, held = login(c, 5, "came"), login(c, 1, "held")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET student_id = '25B000005', email = 'came@kbtu.kz', ms_oid = 'oid-came' WHERE user_id = ?", (came["id"],))
    con.execute("UPDATE students SET student_id = '25B000009', email = 'held@kbtu.kz', ms_oid = 'oid-held' WHERE user_id = ?", (held["id"],))
    lines = ["email,student_id,last,first,middle,school,phone,came",
             "a_one@kbtu.kz,25B010001,Ospanova,Aya,,SITE,,1",            # kept by the main import
             ",25B010007,Bekov,Dana,,ISE,+7 701 000 00 07,1",            # no mail: by ID and name
             "x_mail@gmail.com,25B010008,Shared,One,,,,0",               # an ID another row has too: matches nothing
             "y_mail@kbtu.kz,25B010008,Shared,Two,,,,0",
             "came@kbtu.kz,25B099999,Testov,Came,,,,1",                  # signed up, another ID: badged now
             ",hello,Nobody,Known,,,,0",                                 # neither: it sits
             "h_typo@kbtu.kz,25B000009,Testov,Held,,,,1",                # the ID a student holds, their name: badged now
             "z_gone@kbtu.kz,25B010010,Gone,Zed,,,,1"]                   # kept, then used or deleted

    def run(cmd: str, name: str) -> str:
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(("\n".join(lines) + "\n").encode())))
        capsys.readouterr()
        admin.main([cmd, "--list", name])
        return capsys.readouterr().out
    run("prefill-import", "init26")
    con.execute("DELETE FROM prefill WHERE email = 'z_gone@kbtu.kz'")
    out = run("prefill-rest", "init26")
    assert out.split("\n")[0] == "rows 8  in_prefill 2  gone 1  matched 2  badged 2  stored 3  sits 2"
    assert "kbtu.kz" not in out and "25B" not in out and "Dana" not in out                # counts only
    with pytest.raises(SystemExit):
        run("prefill-rest", "init26")                                                     # each list once
    ach = lambda uid: _ach_codes(c.get(f"/api/users/{uid}", headers=tma(1)).json())  # noqa: E731
    assert ach(came["id"])["init26f"] == 1 and ach(held["id"])["init26f"] == 1
    assert [tuple(r) for r in con.execute("SELECT email, student_id, raw_id FROM prefill_rest ORDER BY raw_id")] == [
        (None, "25B010007", "25B010007"), (None, None, "25B010008"), (None, None, "hello")]
    # Dana signs in with another mail and her own ID: the badge and her phone, the row gone; a namesake's ID row stays
    con.execute("INSERT INTO prefill_rest (student_id, last_name, first_name, came) VALUES ('25B010007', 'Other', 'Person', 1)")
    uid = c.get("/api/me", headers=tma(7)).json()["id"]
    logic.ms_remember(con, uid, {"oid": "oid-7", "email": "d_bekova@kbtu.kz", "first": "Dana", "last": "Bekov", "employeeId": "", "profile": {}})
    assert c.post("/api/kbtu/manual", headers=tma(7), json={"studentId": "25B010007", "consentVersion": logic.CONSENT}).status_code == 200
    assert tuple(con.execute("SELECT student_id, phone, school FROM students WHERE user_id = ?", (uid,)).fetchone()) == ("25B010007", "+77010000007", "ISE")
    assert ach(uid)["init26f"] == 1
    assert [r[0] for r in con.execute("SELECT last_name FROM prefill_rest WHERE student_id = '25B010007'")] == ["Other"]
    con.execute("INSERT INTO prefill_rest (student_id, last_name, first_name) VALUES ('25B010007', 'Bekov', 'Dana')")
    con.execute("INSERT INTO prefill_rest (email, last_name, first_name) VALUES ('d_bekova@kbtu.kz', 'Bekova', 'D')")
    logic.delete_me(con, logic.Viewer(uid, "user", True))
    assert [r[0] for r in con.execute("SELECT last_name FROM prefill_rest WHERE student_id = '25B010007' OR email IS NOT NULL")] == ["Other"]
    con.close()


def test_prefill_rest_review_fixes(env, monkeypatch, capsys):
    """latin-rest-claim-code-review.md (made-up people): the rest import badges a signed-up student and fills nothing (a
    phone they deleted stays deleted); a kept row is gone by its mail, an ID taken after the main import doesn't bring it
    back; a list the main import never ran is refused; two mail-less rows with one ID match by nothing; rows with neither
    mail nor ID go with the account whose name they have; a doubled displayName word is no Latin name."""
    import io
    from pathlib import Path
    from kbtu import admin
    from kbtu.logic.account import latin_from_ms
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    assert latin_from_ms({"displayName": "Aidos Aidos Serikbayev", "givenName": "Aidos", "surname": "Serikbayev"})[0] is None
    ann = login(c, 21, "ann")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE students SET student_id = '25B020001', email = 'ann@kbtu.kz', ms_oid = 'oid-ann' WHERE user_id = ?", (ann["id"],))
    lines = ["email,student_id,last,first,middle,school,phone,came",
             "kept@kbtu.kz,25B020002,Kept,Kim,,,+7 701 000 00 22,1",     # used at sign-in, then the phone deleted
             "gone@kbtu.kz,25B020003,Gone,Gil,,,,1",                     # used, the account deleted; the ID someone's later
             ",25B020009,Shared,Sam,,,,0",                               # no mail, one ID for two people
             ",25B020009,Other,Oleg,,,,0",
             ",,Testov,Ann,,,,0",                                        # neither: goes with Ann's account
             ",,Other,Person,,,,0"]

    def run(cmd: str, name: str) -> str:
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(("\n".join(lines) + "\n").encode())))
        capsys.readouterr()
        admin.main([cmd, "--list", name])
        return capsys.readouterr().out
    run("prefill-import", "l1")
    con.execute("UPDATE meta SET value = ? WHERE key = 'prefill_list:l1'", (str(int(time.time()) - 100),))
    uid = c.get("/api/me", headers=tma(22)).json()["id"]
    logic.ms_remember(con, uid, {"oid": "oid-22", "email": "kept@kbtu.kz", "first": "Kim", "last": "Kept", "employeeId": "", "profile": {}})
    assert c.post("/api/kbtu/manual", headers=tma(22), json={"studentId": "25B020002", "consentVersion": logic.CONSENT}).status_code == 200
    assert c.patch("/api/me", headers=tma(22), json={"phone": None}).status_code == 200
    con.execute("DELETE FROM prefill WHERE email = 'gone@kbtu.kz'")
    bob = login(c, 23, "bob")
    con.execute("UPDATE students SET student_id = '25B020003' WHERE user_id = ?", (bob["id"],))
    with pytest.raises(SystemExit):
        run("prefill-rest", "l2")                                                       # the main import never ran it
    assert run("prefill-rest", "l1").split("\n")[0] == "rows 6  in_prefill 0  gone 1  matched 1  badged 0  stored 4  sits 4"
    assert con.execute("SELECT phone FROM students WHERE user_id = ?", (uid,)).fetchone()[0] is None
    assert [tuple(r) for r in con.execute("SELECT last_name, student_id FROM prefill_rest ORDER BY id")] == [
        ("Shared", None), ("Other", None), ("Testov", None), ("Other", None)]
    logic.delete_me(con, logic.Viewer(ann["id"], "user", True))
    assert [r[0] for r in con.execute("SELECT first_name FROM prefill_rest ORDER BY id")] == ["Sam", "Oleg", "Person"]
    con.close()


def test_claim_link(env, monkeypatch, capsys):
    """The volunteers' badge by a link (prefill-rest-and-claim-review.md B): admin claim new prints a gl_ link many open,
    each student gets it once and at once, a second open is fine, closed after its day or by claim close; one-time
    links work as before."""
    from kbtu import admin
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    boss, ann, bob, cat = login(c, 60, "boss"), login(c, 61, "ann"), login(c, 62, "bob"), login(c, 63, "cat")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600))
    with pytest.raises(SystemExit):
        admin.main(["claim", "new", "bugs", "--until", day])                    # Bug hunter: one by one only
    capsys.readouterr()
    admin.main(["claim", "new", "init26", "--until", day])
    link = capsys.readouterr().out.split("\n")[0]
    token = re.fullmatch(r"https://t\.me/\w+\?startapp=gl_([0-9a-f]{24})", link)[1]
    use = lambda tg: c.post(f"/api/grant-links/{token}", headers=tma(tg)).json()  # noqa: E731
    assert use(61) == use(62) == use(61) == {"code": "init26"}                   # many, and again is fine
    n = lambda uid: con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'init26'", (uid,)).fetchone()[0]  # noqa: E731
    assert (n(ann["id"]), n(bob["id"])) == (1, 1)
    assert con.execute("SELECT expires_at FROM grant_links WHERE token = ?", (token,)).fetchone()[0] > time.time()
    admin.main(["claim", "close", token])
    assert use(63)["error"] == "closed" and n(cat["id"]) == 0
    one_time = logic.grant_link(con, logic.Viewer(boss["id"], "admin", True), "creator_laugh")
    assert c.post(f"/api/grant-links/{one_time}", headers=tma(61)).json() == {"code": "creator_laugh"}
    assert c.post(f"/api/grant-links/{one_time}", headers=tma(62)).json()["error"] == "closed"
    con.close()


def test_name_one_letter_off():
    """A name word one letter off KBTU's own (added, dropped, changed) is a spelling, 4+ letters (owner, Nov 3)."""
    from kbtu.logic.account import _one_off
    assert _one_off("amelie", {"ameli", "sakenova"}) and _one_off("ameli", {"amelie"}) and _one_off("aidas", {"aidos"})
    assert not _one_off("aidan", {"aidos"}) and not _one_off("bekzat", {"aidos"}) and not _one_off("ana", {"an"})
