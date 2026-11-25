"""Friends and referrals."""
from __future__ import annotations

import time

from kbtu import db, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)


def test_friends(env):
    """Friends (SPEC §4.7): a request and its answer, a mutual ask that settles itself, a quiet decline that keeps
    looking pending, a one-time link (the first one wins), where friends go (only if they allow it), unfriend."""
    c, cfg = env
    ali, zhan, dana = login(c, 31, "ali"), login(c, 32, "zhan"), login(c, 33, "dana")
    A, Z, D = tma(31, "Ali"), tma(32, "Zhan"), tma(33, "Dana")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET tg_username = 'zhan_k' WHERE tg_id = 32")
    found = c.get("/api/friends/find?username=@ZHAN_K", headers=A).json()                 # @username, any case
    assert found["person"]["id"] == zhan["id"] and found["friendship"] == "none"
    assert [tuple(r) for r in con.execute("SELECT viewer_id, user_id FROM profile_views")] == [(ali["id"], zhan["id"])]  # a stranger's name: counted
    assert c.get("/api/friends/find?username=nobody_here", headers=A).status_code == 404
    assert c.post("/api/friends/requests", headers=A, json={"userId": zhan["id"]}).json()["friendship"] == "requested"
    assert c.get(f"/api/users/{ali['id']}", headers=Z).json()["friendship"] == "incoming"
    assert c.get("/api/me", headers=Z).json()["counters"]["friendRequests"] == 1
    out = c.post(f"/api/friends/requests/{ali['id']}/accept", headers=Z).json()
    assert [(x["person"]["id"], x["fullName"]) for x in out["friends"]] == [(ali["id"], "Ali Testov")]
    assert c.get(f"/api/users/{zhan['id']}", headers=A).json()["friendship"] == "friends"
    assert [r[0] for r in con.execute("SELECT kind FROM bot_outbox ORDER BY id")] == ["friend_request", "friend_new"]
    # a quiet decline: Dana keeps seeing "requested", and asking again changes nothing
    c.post("/api/friends/requests", headers=D, json={"userId": ali["id"]})
    assert c.post(f"/api/friends/requests/{dana['id']}/decline", headers=A).json()["incoming"] == []
    assert c.get(f"/api/users/{ali['id']}", headers=D).json()["friendship"] == "requested"
    assert c.post("/api/friends/requests", headers=D, json={"userId": ali["id"]}).json()["friendship"] == "requested"
    assert c.get("/api/friends", headers=A).json()["incoming"] == []
    # taking it back after the quiet decline: gone from my list for good (it came back on the next load), the 30 days still
    # held: asking again shows "requested" to me and tells Ali nothing
    assert [r["person"]["id"] for r in c.get("/api/friends", headers=D).json()["outgoing"]] == [ali["id"]]
    assert c.delete(f"/api/friends/requests/{ali['id']}", headers=D).status_code == 204
    assert c.get("/api/friends", headers=D).json()["outgoing"] == [] and c.get(f"/api/users/{ali['id']}", headers=D).json()["friendship"] == "none"
    assert c.post("/api/friends/requests", headers=D, json={"userId": ali["id"]}).json()["friendship"] == "requested"
    assert c.get("/api/friends", headers=A).json()["incoming"] == [] and len(c.get("/api/friends", headers=D).json()["outgoing"]) == 1
    # asking someone who already asked me is the answer
    c.post("/api/friends/requests", headers=Z, json={"userId": dana["id"]})
    assert c.post("/api/friends/requests", headers=D, json={"userId": zhan["id"]}).json()["friendship"] == "friends"
    # where friends go: only those who let friends see it
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (7, 1, 'published', 'Hack', '305', ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (int(time.time()) + 86400,))
    assert c.post("/api/events/7/registration", headers=Z).status_code == 200
    going = c.get("/api/friends", headers=A).json()["going"]
    assert [(e["id"], [p["id"] for p in e["friends"]]) for e in going] == [(7, [zhan["id"]])]
    # a team-only event Zhan goes to (Zhan is in the club, Ali isn't) shows on neither Ali's feed nor Zhan's card for Ali
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'member', 0)", (zhan["id"],))
    con.execute("""INSERT INTO events (id, org_id, status, visibility, title, place, starts_at, emoji, color, created_at, updated_at)
        VALUES (8, 1, 'published', 'members', 'Team retro', '305', ?, 'laptop_3d', '#3B6BFF', 0, 0)""", (int(time.time()) + 86400,))
    assert c.post("/api/events/8/registration", headers=Z).status_code == 200
    assert [e["id"] for e in c.get("/api/friends", headers=A).json()["going"]] == [7]
    assert [e["id"] for e in c.get(f"/api/users/{zhan['id']}", headers=A).json()["going"]] == [7]
    c.patch("/api/me", headers=Z, json={"showGoing": False})
    assert c.get("/api/friends", headers=A).json()["going"] == []
    assert c.delete(f"/api/friends/{zhan['id']}", headers=A).status_code == 204                # quietly
    assert c.get(f"/api/users/{zhan['id']}", headers=A).json()["friendship"] == "none"


def test_can_friend_off(env):
    """"Can add me as a friend" off (owner, Nov 2): no new requests to me (no bot message either), the card and the
    @username search say so; a request already waiting stays mine to accept, and my own asks still work."""
    c, cfg = env
    ali, zhan, dana = login(c, 51, "ali"), login(c, 52, "zhan"), login(c, 53, "dana")
    A, Z, D = tma(51, "Ali"), tma(52, "Zhan"), tma(53, "Dana")
    con = db.connect(cfg.db_path)
    assert c.get("/api/me", headers=Z).json()["settings"]["canFriend"] is True       # on by default
    assert "closed" not in c.get(f"/api/users/{zhan['id']}", headers=A).json()
    c.post("/api/friends/requests", headers=D, json={"userId": zhan["id"]})          # asked before the switch
    assert c.patch("/api/me", headers=Z, json={"canFriend": False}).json()["settings"]["canFriend"] is False
    assert c.get(f"/api/users/{zhan['id']}", headers=A).json()["closed"] is True
    con.execute("UPDATE users SET tg_username = 'zhan_k' WHERE tg_id = 52")
    assert c.get("/api/friends/find?username=zhan_k", headers=A).json()["closed"] is True
    r = c.post("/api/friends/requests", headers=A, json={"userId": zhan["id"]})
    assert r.status_code == 409 and r.json()["error"] == "closed"
    assert [r[0] for r in con.execute("SELECT kind FROM bot_outbox")] == ["friend_request"]  # Dana's only
    assert "closed" not in c.get(f"/api/users/{zhan['id']}", headers=D).json()     # Dana waits: "requested"
    assert c.post(f"/api/friends/requests/{dana['id']}/accept", headers=Z).status_code == 200
    assert c.post("/api/friends/requests", headers=Z, json={"userId": ali["id"]}).json()["friendship"] == "requested"
    assert c.post("/api/friends/requests", headers=A, json={"userId": zhan["id"]}).json()["friendship"] == "friends"  # the answer to mine


def test_referrals(env):
    """Invite links (PLAN): r_<badge code>, never a user ID; the first link wins, only before the KBTU
    sign-in; it counts once the invitee is confirmed by Microsoft; "Recruiter" at 3; gone with the account."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    ann = login(c, 100, "ann")
    code = ann["referrals"]["code"]
    assert ann["referrals"] == {"count": 0, "code": code} and len(code) == 10
    other = login(c, 101, "ole")["referrals"]["code"]
    refer = lambda tg, cd: c.post("/api/referral", headers=tma(tg), json={"code": cd}).status_code  # noqa: E731
    assert refer(100, code) == 204 and con.execute("SELECT referred_by FROM users WHERE tg_id = 100").fetchone()[0] is None  # not myself
    assert refer(101, code) == 204 and con.execute("SELECT referred_by FROM users WHERE tg_id = 101").fetchone()[0] is None  # signed in already
    assert refer(102, "nope") == 400
    for tg in (102, 103, 104, 105):
        c.get("/api/me", headers=tma(tg))
        assert refer(tg, code) == 204
    assert refer(102, other) == 204                                                     # the first link wins
    assert con.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (ann["id"],)).fetchone()[0] == 4
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 0          # Telegram accounts alone count nothing
    def confirm(tg):  # typed in, then Microsoft (app.py's two steps)
        uid = con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]
        con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, manual, synced_at, verified_at)
            VALUES (?, ?, 'X', 'Testov', 1, '1', 0, 1, 0, 0)""", (uid, f"25B{tg:06d}"))
        logic.ms_link(con, uid, {"oid": f"o{tg}", "email": f"x{tg}@kbtu.kz", "first": "X", "last": "Testov"})
    for tg in (102, 103):
        confirm(tg)
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 2
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'referral'", (ann["id"],)).fetchone()[0] == 1
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref = 'ach:referral:1'", (ann["id"],)).fetchone()
    confirm(104)
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'referral'", (ann["id"],)).fetchone()[0] == 2
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND ref = 'ach:referral:2'", (ann["id"],)).fetchone()
    delete_now(c, cfg, tma(103))                                                         # one of them leaves: no longer counted
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 2


def test_invite_link_adds_friend(env):
    """One invite link (Nov 2): r_<link code> opens the inviter's card; opening adds nobody, one tap on its button
    makes friends at once (no request); my own link, friends already, a quiet decline and the day's limit; a newcomer
    still counts as the inviter's referral."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    ann, bob = login(c, 200, "ann"), login(c, 201, "bob")
    A, B = tma(200, "Ann"), tma(201, "Bob")
    code = ann["referrals"]["code"]
    card = c.get(f"/api/invite/{code}", headers=B).json()
    assert card["person"]["id"] == ann["id"] and card["friendship"] == "none"
    assert card["registered"] is True
    c.post("/api/referral", headers=B, json={"code": code})
    assert c.get(f"/api/users/{ann['id']}", headers=B).json()["friendship"] == "none"          # opening adds nobody
    assert c.get(f"/api/invite/{code}", headers=A).json()["friendship"] == "self"
    assert c.post(f"/api/invite/{code}", headers=A).status_code == 400                         # my own link
    assert c.get("/api/invite/AAAAAAAAAA", headers=B).status_code == 404
    since = int(time.time()) - 5
    added = c.post(f"/api/invite/{code}", headers=B).json()
    assert added["friendship"] == "friends" and added["created"] is True
    assert c.get("/api/me", headers=A).json()["referrals"]["count"] == 0                       # Bob was registered already
    assert c.get(f"/api/users/{bob['id']}", headers=A).json()["friendship"] == "friends"
    assert con.execute("SELECT kind FROM bot_outbox WHERE user_id = ?", (ann["id"],)).fetchone()[0] == "friend_new"
    assert c.get(f"/api/friends/joined?since={since}", headers=A).json()["usedBy"]["id"] == bob["id"]  # her QR sheet celebrates
    assert c.get(f"/api/invite/{code}", headers=B).json()["friendship"] == "friends"
    again = c.post(f"/api/invite/{code}", headers=B).json()
    assert again["friendship"] == "friends" and again["created"] is False
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE user_id = ?", (ann["id"],)).fetchone()[0] == 1
    # a guest sees whose link it is; the tap needs the KBTU sign-in; their referral is noted as before
    guest = c.get(f"/api/invite/{code}", headers=tma(202)).json()
    assert guest["friendship"] == "none" and guest["registered"] is False
    assert c.post(f"/api/invite/{code}", headers=tma(202)).json()["error"] == "need_student"
    assert c.post("/api/referral", headers=tma(202), json={"code": code}).status_code == 204
    assert con.execute("SELECT referred_by FROM users WHERE tg_id = 202").fetchone()[0] == ann["id"]
    login(c, 202, "eve")
    assert c.post(f"/api/invite/{code}", headers=tma(202)).json()["created"] is True
    assert c.get("/api/me", headers=A).json()["referrals"]["count"] == 1
    # a request Ann quietly declined holds: her link doesn't get around it
    cat = login(c, 203, "cat")
    C = tma(203, "Cat")
    c.post("/api/friends/requests", headers=C, json={"userId": ann["id"]})
    c.post(f"/api/friends/requests/{cat['id']}/decline", headers=A)
    declined = c.post(f"/api/invite/{code}", headers=C).json()
    assert declined["friendship"] == "requested" and declined["created"] is False
    assert c.get(f"/api/users/{ann['id']}", headers=C).json()["friendship"] == "requested"
    # the day's limit: a stranger can't collect posted links for friends' full names
    now = int(time.time())
    con.executemany("INSERT INTO users (tg_id, created_at, seen_at) VALUES (?, 0, 0)", [(900 + i,) for i in range(logic.FRIEND_ASKS_A_DAY)])
    con.execute("INSERT INTO friendships (a, b, created_at) SELECT ?, id, ? FROM users WHERE tg_id >= 900", (bob["id"], now))
    dan = login(c, 204, "dan")["referrals"]["code"]
    assert c.post(f"/api/invite/{dan}", headers=B).json()["error"] == "rate_limited"


def test_referral_by_profile_qr(env):
    """The profile QR (u_<id>_<badge code>) is an invite link too: a newcomer counts once; a student already signed
    in, myself, a wrong code or a code under another ID count nothing."""
    c, cfg = env
    con = db.connect(cfg.db_path)
    ann, ole = login(c, 100, "ann"), login(c, 101, "ole")
    qr = ann["qr"]
    refer = lambda tg, cd: c.post("/api/referral", headers=tma(tg), json={"code": cd}).status_code  # noqa: E731
    by = lambda tg: con.execute("SELECT referred_by FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    assert refer(100, qr) == 204 and by(100) is None                                    # not myself
    assert refer(101, qr) == 204 and by(101) is None                                    # signed in already
    c.get("/api/me", headers=tma(102))
    assert refer(102, f"{ole['id']}_{qr.split('_')[1]}") == 204 and by(102) is None     # the code is Ann's, not Ole's
    assert refer(102, f"{ann['id']}_AAAAAAAAAA") == 204 and by(102) is None
    assert refer(102, qr) == 204 and by(102) == ann["id"]
    assert refer(102, ole["qr"]) == 204 and refer(102, qr) == 204 and by(102) == ann["id"]  # the first wins, never twice
    uid = con.execute("SELECT id FROM users WHERE tg_id = 102").fetchone()[0]
    con.execute("""INSERT INTO students (user_id, student_id, first_name, last_name, course, consent_version, consent_at, manual, synced_at, verified_at)
        VALUES (?, '25B000102', 'X', 'Testov', 1, '1', 0, 1, 0, 0)""", (uid,))
    logic.ms_link(con, uid, {"oid": "o102", "email": "x102@kbtu.kz", "first": "X", "last": "Testov"})
    assert c.get("/api/me", headers=tma(100)).json()["referrals"]["count"] == 1
