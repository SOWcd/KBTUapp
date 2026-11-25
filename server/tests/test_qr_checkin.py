"""QR check-in and the big screen."""
from __future__ import annotations

import hashlib
import time

from kbtu import db, logic
from test_core import _club_runs, _csv, _paired, env, login, tma  # noqa: F401  (env: the fixture)


def test_qr_checkin(env, monkeypatch):
    """The big screen's QR (checkin.py): paired from the organizer's phone, a scan before the sign-up waits and counts once the
    student signs up (ID prefilled from the organizers' list), a forged or stale QR is refused, the CSV has both."""
    from kbtu import checkin
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    sid = checkin.new(con, "Meeting", [{"email": "S_New@kbtu.kz", "name": "New Person", "studentId": "24B030001"},
                                       {"email": "s_gone@kbtu.kz", "name": "Gone Person"}], org)
    k = _paired(c, 9)                                                                       # Dana's only session
    assert c.get("/api/screen", headers={"X-Screen": "bad"}).status_code == 403
    assert c.get("/api/screen", headers=k).json()["param"] is None                          # not started: no QR
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    con.execute("UPDATE students SET verified_at = verified_at - 60")                     # Ann: a student well before Start
    con.execute("UPDATE qr_sessions SET started_at = started_at - 30")                    # and Start a while ago
    forged = p[:-1] + ("1" if p[-1] == "0" else "0")
    assert c.post("/api/checkin", headers=tma(1), json={"p": forged}).json()["message"] == "qr"   # forged
    _, s, slot, _ = p.split("_")
    old = f"ci_{s}_{int(slot) - 40}_{checkin._sig(cfg.token_key, f'ci.{s}.{int(slot) - 40}')}"
    assert c.post("/api/checkin", headers=tma(1), json={"p": old}).json()["message"] == "qr_old"  # 400 s ago
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]           # a student: at once
    assert not c.post("/api/checkin", headers=tma(2), json={"p": p}).json()["done"]       # not yet: waits
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]           # Ann again: still one mark
    assert not c.post("/api/checkin", headers=tma(2), json={"p": p}).json()["done"]
    st = c.get("/api/screen", headers=k).json()
    assert (st["done"], st["pending"], st["expected"]) == (1, 1, 2)
    uid = c.get("/api/me", headers=tma(2)).json()["id"]
    logic.ms_remember(con, uid, {"oid": "oid-2", "email": "s_new@kbtu.kz", "first": "New", "last": "Person", "employeeId": "", "profile": {}})
    assert c.get("/api/me", headers=tma(2)).json()["msPending"]["prefill"] == {"studentId": "24B030001"}
    r = c.post("/api/kbtu/manual", headers=tma(2), json={"studentId": "24B030001", "consentVersion": logic.CONSENT})
    assert r.status_code == 200, r.text
    assert c.get("/api/screen", headers=k).json()["done"] == 2
    c.post(f"/api/screens/{sid}/finish", headers=tma(9))
    assert c.post("/api/checkin", headers=tma(3), json={"p": p}).status_code == 409       # finished
    rows_ = _csv(c, 9, sid).splitlines()
    assert [r.split(",")[0] for r in rows_[1:]] == ["came", "came (not on the list)", "absent"]   # the list's people first (checkin.export)
    assert rows_[1].split(",")[13] == "B" and rows_[2].split(",")[13] == "A"                     # the tier column
    con.close()


def test_qr_checkin_edges(env, monkeypatch):
    """The review's holes: a non-ASCII QR is a 400 (not a 500), Finish doesn't
    lose who scanned (30 min to sign in, Microsoft's path too), Start doesn't reopen, the CSV has no formulas and
    matches the list by student ID when the mail differs."""
    from kbtu import checkin
    c, cfg = env
    login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    sid = checkin.new(con, "Initiation", [{"email": "ann.home@gmail.com", "name": "=Ann Testov", "studentId": "24Bann",
                                            "phone": "+7 (700) 000-00-00"}], _club_runs(c, con, 9, "dana"))
    k = _paired(c, 9)
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p[:-1] + "\u0436"}).status_code == 400
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["done"]
    for u in (2, 4):
        assert not c.post("/api/checkin", headers=tma(u), json={"p": p}).json()["done"]  # scanned, not signed in yet
    c.post(f"/api/screens/{sid}/finish", headers=tma(9))
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"] is None    # finished stays finished
    assert c.post("/api/checkin", headers=tma(3), json={"p": p}).status_code == 409       # new after Finish: no
    import csv
    rows_ = list(csv.reader(_csv(c, 9, sid).splitlines()))
    assert [r[0] for r in rows_[1:]] == ["came", "scanned, not signed in", "scanned, not signed in"]   # by ID: not absent
    assert (rows_[1][1], rows_[1][10]) == ("'=Ann Testov", "'+7 (700) 000-00-00")     # no formulas in Excel
    assert c.post("/api/checkin", headers=tma(2), json={"p": p}).status_code == 200       # had a mark: may come back
    uid2, uid4 = (c.get("/api/me", headers=tma(u)).json()["id"] for u in (2, 4))
    logic.ms_remember(con, uid2, {"oid": "oid-2", "email": "two@kbtu.kz", "first": "Two", "last": "Person", "employeeId": "", "profile": {}})
    assert c.post("/api/kbtu/manual", headers=tma(2), json={"studentId": "24B030002", "consentVersion": logic.CONSENT}).status_code == 200
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B030004', 'Four', 'P', 1, ?, 0, 0, 0, 1)""", (uid4, logic.CONSENT))
    logic.ms_link(con, uid4, {"oid": "oid-4", "email": "four@kbtu.kz", "first": "Four", "last": "P"})  # the relink path
    st = c.get("/api/screen", headers=k).json()
    assert (st["done"], st["pending"]) == (3, 0)
    con.execute("UPDATE qr_sessions SET ended_at = ended_at - ? WHERE id = ?", (checkin.GRACE + 1, sid))
    assert c.post("/api/checkin", headers=tma(2), json={"p": p}).status_code == 409       # past the grace: closed
    con.close()


def test_screen_pairing(env, monkeypatch):
    """/show without a PIN (Oct 29 night): only a session's organizers bind a screen, a stranger's scan changes nothing,
    a paired screen can't be moved to another club's session, the screen never controls or downloads anything, the CSV
    link is the organizer's and short-lived, "disconnect" sends every screen back to pairing."""
    from kbtu import checkin
    c, cfg = env
    con = db.connect(cfg.db_path)
    vol, other = _club_runs(c, con, 9, "dana"), _club_runs(c, con, 8, "omar", "inc")
    login(c, 1, "ann")                                                                       # a student in the hall
    sid = checkin.new(con, "Initiation", [{"email": "x@kbtu.kz", "name": "X Person", "phone": "+7 (700) 000 00 00"}], vol)
    scr = c.post("/api/screen/pair").json()
    me = {"X-Screen": scr["secret"]}
    assert set(c.get("/api/screen", headers=me).json()) == {"code", "left"}                 # waiting: just its QR
    for uid in (1, 8, 3):                                                                    # a student, another club, a guest
        assert c.post("/api/screens/bind", headers=tma(uid), json={"code": scr["code"]}).status_code == 403
        assert c.post("/api/screens/bind", headers=tma(uid), json={"code": scr["code"], "session": sid}).status_code == 403
    assert "session" not in c.get("/api/screen", headers=me).json()                         # still Dana's to pair
    assert c.get("/api/screens", headers=tma(1)).json() == [] and c.get("/api/screens", headers=tma(8)).json() == []
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": scr["code"]}).json()["session"] == sid
    assert c.get("/api/screen", headers=me).json()["session"] == sid
    theirs = checkin.new(con, "Their party", [], other)
    assert c.post("/api/screens/bind", headers=tma(8), json={"code": scr["code"], "session": theirs}).status_code == 403  # not moved
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": scr["code"], "session": theirs}).json()["session"] == sid
    for act in ("start", "finish", "unpair", "csv"):                                         # nobody else runs it
        assert c.post(f"/api/screens/{sid}/{act}", headers=tma(1)).status_code == 403
    assert c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": c.get("/api/screen", headers=me).json()["param"]}).json()["done"]
    url = c.post(f"/api/screens/{sid}/csv", headers=tma(9)).json()["url"]
    assert c.get(url.replace("k=", "k=0")).status_code == 403 and c.get(url).status_code == 200
    e = int(url.split("e=")[1].split("&")[0])
    monkeypatch.setattr(checkin, "now", lambda: e + 1)
    assert c.get(url).status_code == 403                                                     # the link is short-lived
    monkeypatch.undo()
    # a stale pairing QR (a photo of it) binds nothing
    old = c.post("/api/screen/pair").json()
    con.execute("UPDATE qr_screens SET created_at = created_at - ? WHERE code = ?", (checkin.PAIR_TTL + 1, old["code"]))
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": old["code"]}).status_code == 404
    # several open sessions: the app has to say which
    sid2 = checkin.new(con, "Second", [], vol)
    two = c.post("/api/screen/pair").json()
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": two["code"]}).json()["message"] == "pick"
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": two["code"], "session": sid2}).json()["session"] == sid2
    assert c.post(f"/api/screens/{sid}/unpair", headers=tma(9)).json()["screens"] == 0
    assert c.get("/api/screen", headers=me).status_code == 403                               # back to a new pairing QR
    assert c.get("/api/screen", headers={"X-Screen": two["secret"]}).json()["session"] == sid2
    # two binds of one pairing QR at once (codex ideas2 2): the loser is not told its session got the screen
    sid3 = checkin.new(con, "Third", [], vol)
    race = c.post("/api/screen/pair").json()
    real = checkin._mine
    def first_wins(con_, v, s_id, cohost=True, door=False):  # the other request binds it between our read and our write
        con_.execute("UPDATE qr_screens SET session_id = ? WHERE code = ?", (sid2, race["code"]))
        return real(con_, v, s_id, cohost, door)
    monkeypatch.setattr(checkin, "_mine", first_wins)
    assert c.post("/api/screens/bind", headers=tma(9), json={"code": race["code"], "session": sid3}).json()["session"] == sid2
    monkeypatch.setattr(checkin, "_mine", real)
    monkeypatch.setattr(checkin, "PAIR_PER_IP", 1)
    other = {"cf-connecting-ip": "203.0.113.9"}
    assert c.post("/api/screen/pair", headers=other).status_code == 200
    assert c.post("/api/screen/pair", headers=other).status_code == 429                      # one address can't take them all
    assert c.post("/api/screen/pair", headers={"cf-connecting-ip": "203.0.113.10"}).status_code == 200
    assert c.post("/api/screen/pair", headers={"cf-connecting-ip": "2001:db8:1:2::1"}).status_code == 200
    assert c.post("/api/screen/pair", headers={"cf-connecting-ip": "2001:db8:1:2:ffff::9"}).status_code == 429  # one IPv6 /64 is one address
    import hashlib
    plain = hashlib.sha256(b"kbtu-ip:203.0.113.10").hexdigest()[:16]
    assert not con.execute("SELECT 1 FROM qr_screens WHERE ip = ?", (plain,)).fetchone()                  # keyed, not a plain hash
    monkeypatch.setattr(checkin, "PAIR_MAX", 1)
    c.post("/api/screen/pair")                                                               # one waiting: the cap
    assert c.post("/api/screen/pair").status_code == 429                                     # junk can't fill the table
    con.close()


def test_event_screen(env):
    """An event's own check-in screen (Oct 30): its organizers make it in the app (one per event); a counted scan is
    that event's check-in (a walk-in on a free public event, the ticket checked in, nothing on a paid one without one); a
    partner's event keeps its door."""
    from kbtu import checkin
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    t0 = int(time.time())
    for eid, price, host in ((1, None, None), (2, 2000, None), (3, None, "Night Owls")):
        con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, price, pay_to_name, pay_phone, guest_host,
            created_by, created_at, updated_at) VALUES (?, ?, 'published', 'Initiation', 'Hall', ?, 'trophy_3d', '#3B6BFF', ?, ?, ?, ?, 1, 0, 0)""",
                    (eid, org, t0 + 600, price, price and "Dana S.", price and "+77071234567", host))
    assert c.post("/api/events/1/screen", headers=tma(1)).status_code == 403                 # a guest at it, not its organizer
    assert c.post("/api/events/3/screen", headers=tma(9)).status_code == 409                # a partner's: no door
    # a paid one too, from any member at its door (owner, Nov 10): a guest who can't open the ticket scans this QR instead
    mem = login(c, 7, "mia")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, mem["id"]))
    q = c.post("/api/events/2/screen", headers=tma(7)).json()
    assert c.post(f"/api/screens/{q['session']}/start", headers=tma(7)).status_code == 200
    qp = c.post(f"/api/screens/{q['session']}/show", headers=tma(7)).json()["param"]
    assert c.post(f"/api/screens/{q['session']}/finish", headers=tma(7)).status_code == 403  # finishing stays the organizers'
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (2, ?, 'going', 'T2', 0, 0)", (bob["id"],))
    assert c.post("/api/checkin", headers=tma(2), json={"p": qp}).json()["done"]           # Bob's paid ticket
    assert not c.post("/api/checkin", headers=tma(1), json={"p": qp}).json()["done"]       # no ticket, no way in
    assert [tuple(r) for r in con.execute("SELECT user_id FROM registrations WHERE event_id = 2 AND checked_in_at IS NOT NULL").fetchall()] == [(bob["id"],)]
    con.execute("UPDATE events SET starts_at = ? WHERE id = 2", (t0 + 86400,))              # the door not open yet: a member can't
    assert c.post(f"/api/screens/{q['session']}/show", headers=tma(7)).json()["message"] == "not_open"  # said when it opens
    s = c.post("/api/events/1/screen", headers=tma(9)).json()
    assert (s["event"], s["title"]) == (1, "Initiation") and c.post("/api/events/1/screen", headers=tma(9)).json()["session"] == s["session"]
    p = c.post(f"/api/screens/{s['session']}/start", headers=tma(9)).json()["param"]
    c.post("/api/events/1/registration", headers=tma(2), json={})                            # Bob has a ticket
    for u in (1, 2):
        r = c.post("/api/checkin", headers=tma(u), json={"p": p}).json()
        assert r["done"] and r["event"] == 1 and not r["again"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["again"]             # the same scan twice: "already"
    came = dict(con.execute("SELECT user_id, walk_in FROM registrations WHERE event_id = 1 AND checked_in_at IS NOT NULL").fetchall())
    assert came == {ann["id"]: 1, bob["id"]: 0}                                              # Ann walked in, Bob's ticket
    # a scan before the sign-up counts for the event once that person is a student
    assert not c.post("/api/checkin", headers=tma(4), json={"p": p}).json()["done"]
    uid = c.get("/api/me", headers=tma(4)).json()["id"]
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, verified_at,
        synced_at, manual) VALUES (?, '24B4', 'Four', 'P', 1, ?, 0, 0, 0, 1)""", (uid, logic.CONSENT))
    with db.tx(con):
        checkin.became_student(con, uid)
    assert con.execute("SELECT checked_in_at IS NOT NULL FROM registrations WHERE event_id = 1 AND user_id = ?", (uid,)).fetchone()[0]
    # far from the door's window (a session started a week early): a guest's scan is refused before any mark (one QR at
    # the door: no count the team's early scans would be mixed into), told when it opens
    con.execute("UPDATE events SET starts_at = starts_at + 7 * 86400 WHERE id = 1")
    login(c, 5, "eve")
    k = _paired(c, 9, s["session"])                                                          # a laptop on the event's session
    r = c.post("/api/checkin", headers=tma(5), json={"p": c.get("/api/screen", headers=k).json()["param"]})
    assert r.status_code == 409 and r.json()["message"] == "not_open"                        # not told "checked in"
    assert not con.execute("SELECT 1 FROM registrations r JOIN users u ON u.id = r.user_id WHERE u.tg_id = 5").fetchone()
    assert not con.execute("SELECT 1 FROM qr_marks m JOIN users u ON u.id = m.user_id WHERE u.tg_id = 5").fetchone()
    con.close()


def test_checkin_way_out(env, monkeypatch):
    """Oct 30: the initiation's volunteers mark leaving on the same screen (the organizer switches it to "out"): the CSV
    has when each left and the hours; the owner then gives everyone counted the "init26" badge, once each."""
    import csv
    from kbtu import checkin
    c, cfg = env
    con = db.connect(cfg.db_path)
    org = _club_runs(c, con, 9, "dana")
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    sid = checkin.new(con, "Initiation", [], org)
    k = _paired(c, 9)
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    for u in (1, 2):
        assert c.post("/api/checkin", headers=tma(u), json={"p": p}).json()["left"] is False
    con.execute("UPDATE qr_marks SET done_at = done_at - 7200")                                # came two hours ago
    assert c.post(f"/api/screens/{sid}/out", headers=tma(1)).status_code == 403              # a student can't switch it
    assert c.post(f"/api/screens/{sid}/out", headers=tma(9)).json()["phase"] == "out"
    p = c.get("/api/screen", headers=k).json()["param"]
    assert c.post("/api/checkin", headers=tma(1), json={"p": p}).json()["left"] is True
    assert c.get("/api/screen", headers=k).json()["departed"] == 1
    # the adversarial review: a "leaving" scan alone isn't being there (no mark, no badge); an old link from Telegram's
    # history can't mark leaving from home
    cleo = login(c, 3, "cleo")
    r = c.post("/api/checkin", headers=tma(3), json={"p": p})
    assert (r.status_code, r.json()["message"]) == (400, "qr_not_in") and not con.execute("SELECT 1 FROM qr_marks WHERE user_id = ?", (cleo["id"],)).fetchone()
    was = int(time.time()) // checkin.SLOT - 20
    stale = f"ci_{sid}_{was}_{checkin._sig(cfg.token_key, f'ci.{sid}.{was}')}"
    assert c.post("/api/checkin", headers=tma(2), json={"p": stale}).json()["message"] == "qr_old"
    rows_ = list(csv.reader(_csv(c, 9, sid).splitlines()))
    ann_row = next(r for r in rows_[1:] if r[7] == "24Bann")
    assert ann_row[14] and float(ann_row[15]) >= 1.9 and not next(r for r in rows_[1:] if r[7] == "24Bbob")[14]
    # the badge: the owner only, everyone counted, once
    assert c.post(f"/api/screens/{sid}/grant", headers=tma(9), json={"code": "init26"}).status_code == 403
    login(c, 4, "boss")
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE tg_id = 4")
    assert c.post(f"/api/screens/{sid}/grant", headers=tma(4), json={"code": "init26"}).json()["granted"] == 2
    assert c.post(f"/api/screens/{sid}/grant", headers=tma(4), json={"code": "init26"}).json()["granted"] == 0
    ach = {a["code"]: a["level"] for a in c.get(f"/api/users/{ann['id']}", headers=tma(1)).json()["awards"]["achievements"]}
    assert ach["init26"] == 1
    con.close()
