"""People you may know (logic/pymk.py): clubmates who both turned it on, counts only, never a barred pair."""
import time

from kbtu import db, logic
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)


def _con(cfg):
    return db.connect(cfg.db_path)


def _club(con, oid: int, *uids: int, hidden: int = 0, probation: tuple = ()) -> None:
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, members_hidden) VALUES (?, ?, 'club', ?, 'C', 'laptop_3d', 0, ?)",
                (oid, f"c{oid}x", f"Secret Club {oid}", hidden))
    for u in uids:
        con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at, probation) VALUES (?, ?, 'member', 0, ?)", (oid, u, int(u in probation)))


def _on(c, tg: int, on: bool = True) -> dict:
    r = c.patch("/api/me", headers=tma(tg), json={"suggestMe": on})
    assert r.status_code == 200, r.text
    return r.json()


def _sug(c, tg: int):
    s = c.get("/api/friends", headers=tma(tg)).json()["suggest"]
    return None if s is None else [x["person"]["id"] for x in s]


def _night(con) -> None:
    con.execute("DELETE FROM meta WHERE key = 'pymk_day'")
    logic.pymk.night(con)


def test_opt_in_and_reciprocal(env):
    """Off: nothing to see and in nobody's list. On: my list at once; theirs tonight. Off again: gone both ways now.
    The card carries counts only: no club's name or id."""
    c, cfg = env
    ann, ben, cat = login(c, 10, "ann"), login(c, 11, "ben"), login(c, 12, "cat")
    con = _con(cfg)
    _club(con, 1, ann["id"], ben["id"], cat["id"])
    assert _sug(c, 10) is None and c.get("/api/me", headers=tma(10)).json()["settings"]["suggestMe"] is False
    assert _on(c, 10)["settings"]["suggestMe"] is True
    assert _sug(c, 10) == []                                    # nobody else has it on
    _on(c, 11)
    assert _sug(c, 11) == [ann["id"]]                           # worked out for me at once
    assert _sug(c, 10) == []                                    # the others' lists: tonight
    _night(con)
    assert _sug(c, 10) == [ben["id"]]                           # cat never: not turned on
    body = c.get("/api/friends", headers=tma(10))
    card = body.json()["suggest"][0]
    assert set(card) == {"person", "course", "school", "clubs"} and card["clubs"] == 1
    assert "Secret Club" not in body.text and "c1x" not in body.text
    _on(c, 11, False)
    assert _sug(c, 11) is None and _sug(c, 10) == []
    assert not con.execute("SELECT 1 FROM pymk WHERE user_id = ? OR other_id = ?", (ben["id"], ben["id"])).fetchone()
    assert not con.execute("SELECT 1 FROM pymk_consents WHERE user_id = ?", (ben["id"],)).fetchone()
    assert c.patch("/api/me", headers=tma(30, "Gus"), json={"suggestMe": True}).status_code == 401  # a guest can't
    for bad in ("true", 1, {}):                                 # a consent: an explicit yes only
        assert c.patch("/api/me", headers=tma(12), json={"suggestMe": bad}).status_code == 400
    assert c.get("/api/me", headers=tma(12)).json()["settings"]["suggestMe"] is False


def test_switching_again_deals_nothing_new(env):
    """Off and on again the same day: no fresh list past the dismissed ones (the day's TOP holds)."""
    c, cfg = env
    people = [login(c, 10 + i, f"q{i:02d}") for i in range(8)]
    con = _con(cfg)
    _club(con, 1, *(p["id"] for p in people))
    for i in range(1, 8):
        _on(c, 10 + i)
    _on(c, 10)
    for x in list(_sug(c, 10)):
        c.post("/api/pymk/dismiss", headers=tma(10), json={"id": x})
    left = _sug(c, 10)
    _on(c, 10)                                                  # already on: nothing happens
    _on(c, 10, False)
    _on(c, 10)
    assert _sug(c, 10) == [] and len(left) == 2                 # 7 clubmates: 5 dismissed, the 2 left, then nothing till tonight
    _night(con)
    assert _sug(c, 10) == left


def test_card_counts_clubs_as_they_stand_now(env):
    """A club hiding its roster, a probation or a leave since the night: the card no longer counts it."""
    c, cfg = env
    ann, ben, cat = login(c, 10, "ann"), login(c, 11, "ben"), login(c, 12, "cat")
    for tg in (10, 11, 12):
        _on(c, tg)
    con = _con(cfg)
    _club(con, 1, ann["id"], ben["id"], cat["id"])
    _club(con, 2, ann["id"], ben["id"])
    _night(con)
    clubs = lambda: {x["person"]["id"]: x["clubs"] for x in c.get("/api/friends", headers=tma(10)).json()["suggest"]}  # noqa: E731
    assert clubs() == {ben["id"]: 2, cat["id"]: 1}
    con.execute("UPDATE orgs SET members_hidden = 1 WHERE id = 2")
    assert clubs() == {ben["id"]: 1, cat["id"]: 1}
    con.execute("UPDATE org_members SET probation = 1 WHERE org_id = 1 AND user_id = ?", (cat["id"],))
    assert clubs() == {ben["id"]: 1}
    con.execute("DELETE FROM org_members WHERE org_id = 1 AND user_id = ?", (ben["id"],))
    assert clubs() == {}


def test_who_never_appears(env):
    """Requests closed, banned, leaving, a typed-in row or a guest: never suggested, whatever their switch said."""
    c, cfg = env
    ann = login(c, 10, "ann")
    others = [login(c, 11 + i, n) for i, n in enumerate(("ben", "cat", "dan", "eve", "fay"))]
    for i in range(len(others) + 1):
        _on(c, 10 + i)
    gus = c.get("/api/me", headers=tma(30, "Gus")).json()
    con = _con(cfg)
    con.execute("INSERT INTO pymk_consents (user_id, version, at) VALUES (?, ?, 0)", (gus["id"], logic.pymk.CONSENT))
    ben, cat, dan, eve, fay = (p["id"] for p in others)
    _club(con, 1, ann["id"], ben, cat, dan, eve, fay, gus["id"])
    con.execute("UPDATE users SET can_friend = 0 WHERE id = ?", (ben,))
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (cat,))
    con.execute("UPDATE users SET delete_at = ? WHERE id = ?", (int(time.time()) + 86400, dan))
    con.execute("UPDATE students SET manual = 1 WHERE user_id = ?", (eve,))
    _night(con)
    assert _sug(c, 10) == [fay]
    assert _sug(c, 11) == []                                    # requests closed: switched on, yet nothing for me either
    con.execute("UPDATE users SET can_friend = 1 WHERE id = ?", (ben,))
    assert _sug(c, 10) == [fay]                                 # back only with the next recount
    _night(con)
    assert _sug(c, 10) == [ben, fay]


def test_barred_pairs(env):
    """A block either way, a request either way (a decline a year old too), friends, a dismissal by either, an open
    report, an unfriend: never suggested. Checked again when the page loads, not only at night."""
    c, cfg = env
    names = ("ann", "ben", "cat", "dan", "eve", "fay", "gil", "hal", "ivy", "joe")
    people = [login(c, 10 + i, n) for i, n in enumerate(names)]
    for i in range(len(names)):
        _on(c, 10 + i)
    con = _con(cfg)
    ann, ben, cat, dan, eve, fay, gil, hal, ivy, joe = (p["id"] for p in people)
    _club(con, 1, *(p["id"] for p in people))
    now = int(time.time())
    con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (ann, ben))
    con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (cat, ann))
    con.execute("INSERT INTO friend_requests (from_id, to_id, status, created_at, decided_at) VALUES (?, ?, 'declined', ?, ?)", (ann, dan, now - 400 * 86400, now - 399 * 86400))
    con.execute("INSERT INTO friend_requests (from_id, to_id, status, created_at) VALUES (?, ?, 'pending', ?)", (eve, ann, now))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(ann, fay), max(ann, fay)))
    assert c.post("/api/pymk/dismiss", headers=tma(16), json={"id": ann}).status_code == 204  # gil's x on ann
    con.execute("INSERT INTO reports (reporter_id, target, target_id, reason, status, created_at) VALUES (?, 'user', ?, 'insult', 'open', ?)", (hal, ann, now))
    con.execute("INSERT INTO friendships (a, b, created_at) VALUES (?, ?, 0)", (min(ann, ivy), max(ann, ivy)))
    assert c.delete(f"/api/friends/{ivy}", headers=tma(10)).status_code == 204  # an unfriend: not back as a suggestion
    _night(con)
    assert _sug(c, 10) == [joe]
    assert ann not in _sug(c, 11) + _sug(c, 12) + _sug(c, 16) + _sug(c, 17) + _sug(c, 18)
    con.execute("INSERT INTO blocks (user_id, blocked_id, created_at) VALUES (?, ?, 0)", (joe, ann))
    assert _sug(c, 10) == []                                    # at once, not tomorrow
    for bad in ("x", True, ann, None):
        assert c.post("/api/pymk/dismiss", headers=tma(10), json={"id": bad}).status_code == 400
    assert c.post("/api/pymk/dismiss", headers=tma(30, "Gus"), json={"id": ann}).status_code == 401


def test_hidden_probation_and_big_clubs_count_nothing(env):
    """A hidden roster, a member on probation and a crowd of more than BIG say nothing; an open club counts one."""
    c, cfg = env
    ann, ben, cat = login(c, 10, "ann"), login(c, 11, "ben"), login(c, 12, "cat")
    for tg in (10, 11, 12):
        _on(c, tg)
    con = _con(cfg)
    _club(con, 1, ann["id"], ben["id"], hidden=1)
    _club(con, 2, ann["id"], cat["id"], probation=(cat["id"],))
    _club(con, 3, ann["id"], ben["id"])
    crowd = [con.execute("INSERT INTO users (tg_id, created_at, seen_at) VALUES (?, 0, 0)", (900000 + i,)).lastrowid for i in range(logic.pymk.BIG)]
    _club(con, 4, ann["id"], cat["id"], *crowd)
    _night(con)
    s = c.get("/api/friends", headers=tma(10)).json()["suggest"]
    assert [(x["person"]["id"], x["clubs"]) for x in s] == [(ben["id"], 1)]


def test_five_shown_the_next_moves_up_no_paging(env):
    """SHOWN at a time from the night's TOP: a dismissal or a request brings the next; never more than TOP a day.
    Adding is the plain friend request (same notification)."""
    c, cfg = env
    people = [login(c, 10 + i, f"p{i:02d}") for i in range(13)]
    for i in range(13):
        _on(c, 10 + i)
    con = _con(cfg)
    _club(con, 1, *(p["id"] for p in people))
    _night(con)
    first = _sug(c, 10)
    assert len(first) == logic.pymk.SHOWN and c.get("/api/friends?page=2&offset=5", headers=tma(10)).json()["suggest"] == c.get("/api/friends", headers=tma(10)).json()["suggest"]
    r = c.post("/api/friends/requests", headers=tma(10), json={"userId": first[0]}).json()
    assert r["friendship"] == "requested"
    assert con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ? AND kind = 'friend_request'", (first[0],)).fetchone()
    assert first[0] not in _sug(c, 10) and len(_sug(c, 10)) == logic.pymk.SHOWN
    seen = set(first)
    while s := _sug(c, 10):
        seen |= set(s)
        assert c.post("/api/pymk/dismiss", headers=tma(10), json={"id": s[0]}).status_code == 204
    assert len(seen) == logic.pymk.TOP


def test_account_deletion_takes_it_all(env):
    c, cfg = env
    ann, ben, cat = login(c, 10, "ann"), login(c, 11, "ben"), login(c, 12, "cat")
    for tg in (10, 11, 12):
        _on(c, tg)
    con = _con(cfg)
    _club(con, 1, ann["id"], ben["id"], cat["id"])
    _night(con)
    c.post("/api/pymk/dismiss", headers=tma(11), json={"id": ann["id"]})
    c.post("/api/pymk/dismiss", headers=tma(10), json={"id": cat["id"]})
    delete_now(c, cfg, tma(10))
    for t, cols in (("pymk", ("user_id", "other_id")), ("pymk_dismissed", ("user_id", "other_id")), ("pymk_consents", ("user_id",))):
        for col in cols:
            assert not con.execute(f"SELECT 1 FROM {t} WHERE {col} = ?", (ann["id"],)).fetchone(), (t, col)


def test_night_runs_once_a_day_and_fast(env):
    """4,000 opted-in students in two clubs each (clubs at the BIG cap): one pass in seconds, and once per day key."""
    c, cfg = env
    con = _con(cfg)
    n, per = 4000, logic.pymk.BIG
    with db.tx(con):
        ids = [con.execute("INSERT INTO users (tg_id, created_at, seen_at) VALUES (?, 0, 0)", (800000 + i,)).lastrowid for i in range(n)]
        con.executemany("""INSERT INTO students (user_id, student_id, first_name, last_name, course, school, consent_version, consent_at, verified_at, synced_at)
            VALUES (?, ?, 'S', 'T', 2, 'SITE', '1', 0, 0, 0)""", [(u, f"24B{u:06d}") for u in ids])
        con.executemany("INSERT INTO pymk_consents (user_id, version, at) VALUES (?, ?, 0)", [(u, logic.pymk.CONSENT) for u in ids])
        # two layers of full clubs, the second shifted by half a club: everyone in two, each pair of clubs overlapping
        slots = [(100 + i // per, u) for i, u in enumerate(ids)] + [(200 + (i + per // 2) // per, u) for i, u in enumerate(ids)]
        con.executemany("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (?, ?, 'club', 'C', 'C', 'laptop_3d', 0)",
                        [(o, f"big{o}") for o in sorted({o for o, _ in slots})])
        con.executemany("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", slots)
    t0 = time.monotonic()
    _night(con)
    took = time.monotonic() - t0
    assert took < 30, took
    stored = con.execute("SELECT COUNT(*) FROM pymk").fetchone()[0]
    assert 0 < stored <= n * logic.pymk.TOP
    con.execute("DELETE FROM pymk")
    logic.pymk.night(con)                                       # the same day again: nothing runs
    assert con.execute("SELECT COUNT(*) FROM pymk").fetchone()[0] == 0
