"""Department meetups: scans are evidence, membership exceptions are reviewed separately. CI only."""
from __future__ import annotations

import threading

from kbtu import bot, checkin, db, logic, texts
from test_club_checkin import _join
from test_core import _club_runs, env, login, set_clock, tma  # noqa: F401


def _setup(c, con):
    oid = _club_runs(c, con, 9, "dana", "chess")
    president = con.execute("SELECT user_id FROM org_members WHERE org_id = ?", (oid,)).fetchone()[0]
    con.execute("UPDATE org_members SET role = 'president' WHERE org_id = ?", (oid,))
    head = _join(c, con, oid, 8, "head", "head")
    vice = _join(c, con, oid, 7, "vice", "vice")
    free = _join(c, con, oid, 1, "ann", "member")
    inside = _join(c, con, oid, 2, "bob", "member")
    elsewhere = _join(c, con, oid, 3, "cat", "member")
    outsider = login(c, 4, "outsider")["id"]
    tags = [con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, ?, 'blue', 1, 0)",
                        (oid, name)).lastrowid for name in ("Media", "Design")]
    for uid, tag in ((head, tags[0]), (inside, tags[0]), (elsewhere, tags[1])):
        con.execute("INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)", (tag, uid))
    return oid, tags, {9: president, 8: head, 7: vice, 1: free, 2: inside, 3: elsewhere, 4: outsider}


def _start(c, oid, who):
    r = c.post(f"/api/orgs/{oid}/screens", headers=tma(9), json={"who": who})
    assert r.status_code == 200, r.text
    sid = r.json()["session"]
    r = c.post(f"/api/screens/{sid}/start", headers=tma(9))
    assert r.status_code == 200, r.text
    return sid, r.json()["param"]


def _scan(c, tg, p):
    return c.post("/api/checkin", headers=tma(tg), json={"p": p})


def _rows(c, sid, tg=9):
    r = c.get(f"/api/screens/{sid}/scans", headers=tma(tg))
    assert r.status_code == 200, r.text
    return r.json()["rows"]


def _notice(con, sid, uid):
    return con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE kind = 'meetup_review' AND ref = ? AND user_id = ?",
                       (f"meet:{sid}", uid)).fetchone()


def test_every_scan_stays_including_outsiders_and_repeats(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    # A club ban is not a reason to erase attendance at a meetup.
    con.execute("INSERT INTO org_bans (org_id, user_id, by_id, created_at) VALUES (?, ?, ?, 0)", (oid, ids[4], ids[9]))
    sid, p = _start(c, oid, tags[0])
    for tg in (2, 3, 4, 1, 4):
        r = _scan(c, tg, p)
        assert r.status_code == 200 and r.json()["done"], r.text
    scans = _rows(c, sid)
    assert len(scans) == 5 and all(x["at"] > 0 for x in scans)
    flags = {r["user"]: r["flag"] for r in scans}
    assert flags == {ids[2]: None, ids[3]: "department", ids[4]: "outsider", ids[1]: "unassigned"}
    assert len(_rows(c, sid, 7)) == 5
    assert con.execute("SELECT COUNT(*) FROM qr_marks WHERE session_id = ?", (sid,)).fetchone()[0] == 4
    row = next(s for s in c.get('/api/screens', headers=tma(9)).json() if s['session'] == sid)
    assert (row["flagged"], row["scans"], row["department"], row["org"]) == (3, 5, "Media", oid)
    # Whole-club meetups also retain outsiders, without department review.
    whole, p = _start(c, oid, 'club')
    assert _scan(c, 4, p).status_code == 200
    assert _rows(c, whole)[0]["flag"] is None
    con.close()


def test_notification_grouped_once_and_current_at_delivery(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    sid, p = _start(c, oid, tags[0])
    assert _scan(c, 4, p).status_code == 200
    m = _notice(con, sid, ids[8])
    first_scan = con.execute('SELECT scanned_at FROM qr_meet_scans WHERE session_id = ?', (sid,)).fetchone()[0]
    assert m and m["send_after"] == first_scan + 30
    assert bot._render(con, m) == (*texts.bot_message('ru', 'meetup_review', dept='Media'), f'meet_{sid}')
    for tg in (1, 3, 4, 1):
        assert _scan(c, tg, p).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'meetup_review'").fetchone()[0] == 1
    assert bot._render(con, m) == (*texts.bot_message('ru', 'meetup_ask', dept='Media'), f'meet_{sid}')
    con.execute("UPDATE bot_outbox SET sent_at = 1 WHERE id = ?", (m['id'],))
    assert _scan(c, 1, p).status_code == 200
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'meetup_review'").fetchone()[0] == 1
    con.execute("UPDATE member_tags SET sync = 1 WHERE tag_id = ? AND user_id = ?", (tags[0], ids[8]))
    assert bot._render(con, m) is None  # a synced department is not authority to manage it
    con.close()


def test_head_asks_adds_or_declines_without_losing_flags(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    sid, p = _start(c, oid, tags[0])
    assert _scan(c, 1, p).status_code == 200
    assert _scan(c, 1, p).status_code == 200
    assert sum(x['ask'] for x in _rows(c, sid, 8)) == 1
    assert not any(x['ask'] for x in _rows(c, sid, 9))
    url = f'/api/screens/{sid}/scans/{ids[1]}'
    assert c.post(url, headers=tma(8), json={'add': True}).status_code == 200
    assert con.execute('SELECT sync FROM member_tags WHERE user_id = ? AND tag_id = ?', (ids[1], tags[0])).fetchone()[0] == 0
    assert all(x['flag'] == 'unassigned' and x['review'] == 'added' and not x['ask'] for x in _rows(c, sid, 8))
    assert c.post(url, headers=tma(8), json={'add': True}).status_code == 200  # retry
    assert c.post(url, headers=tma(8), json={'add': False}).status_code == 200  # cannot undo through a stale tap
    assert con.execute('SELECT meetup_review FROM qr_marks WHERE session_id = ? AND user_id = ?', (sid, ids[1])).fetchone()[0] == 'added'
    assert _scan(c, 1, p).status_code == 200
    assert _rows(c, sid, 8)[0]['flag'] is None
    other = _join(c, con, oid, 6, 'newcomer', 'member')
    assert _scan(c, 6, p).status_code == 200
    assert c.post(f'/api/screens/{sid}/scans/{other}', headers=tma(8), json={'add': False}).status_code == 200
    assert not con.execute('SELECT 1 FROM member_tags WHERE user_id = ?', (other,)).fetchone()
    assert _scan(c, 6, p).status_code == 200
    assert not any(x['ask'] for x in _rows(c, sid, 8) if x['user'] == other)
    con.close()


def test_no_cross_department_or_club_assignment_and_live_membership_recheck(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    another = _club_runs(c, con, 5, 'eve', 'go')
    foreign = con.execute("INSERT INTO org_tags (org_id, name, color, department, created_at) VALUES (?, 'Foreign', 'red', 1, 0)", (another,)).lastrowid
    plain = con.execute("INSERT INTO org_tags (org_id, name, color, created_at) VALUES (?, 'Label', 'red', 0)", (oid,)).lastrowid
    for who in (foreign, plain, True, 'bad'):
        assert c.post(f'/api/orgs/{oid}/screens', headers=tma(9), json={'who': who}).status_code == 400
    sid, p = _start(c, oid, tags[0])
    for tg in (1, 3, 4):
        assert _scan(c, tg, p).status_code == 200
    url = f'/api/screens/{sid}/scans/{ids[1]}'
    for tg in (1, 4, 5, 9):
        assert c.post(url, headers=tma(tg), json={'add': True}).status_code == 403
    for tg in (1, 4, 5):
        assert c.get(f'/api/screens/{sid}/scans', headers=tma(tg)).status_code == 403
        assert c.get(f'/api/screens/{sid}', headers=tma(tg)).status_code == 403
    assert c.post(f'/api/screens/{sid}/scans/{ids[4]}', headers=tma(8), json={'add': True}).status_code == 403
    assert c.post(f'/api/screens/{sid}/scans/{ids[3]}', headers=tma(8), json={'add': True}).status_code == 404
    con.execute('INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)', (tags[1], ids[1]))
    assert c.post(url, headers=tma(8), json={'add': True}).status_code == 409
    assert not con.execute('SELECT 1 FROM member_tags WHERE tag_id = ? AND user_id = ?', (tags[0], ids[1])).fetchone()
    con.execute('DELETE FROM member_tags WHERE user_id = ?', (ids[8],))
    assert c.post(url, headers=tma(8), json={'add': False}).status_code == 403
    con.close()


def test_pending_scans_departure_only_and_stale_retry(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    sid, p = _start(c, oid, tags[0])
    pending = c.get('/api/me', headers=tma(10)).json()['id']
    r = _scan(c, 10, p)
    assert r.status_code == 200 and not r.json()['done']
    assert _rows(c, sid)[0]['user'] == pending and _rows(c, sid)[0]['flag'] == 'outsider'
    out = c.post(f'/api/screens/{sid}/out', headers=tma(9)).json()['param']  # each phase has its own QR
    departure = c.get('/api/me', headers=tma(11)).json()['id']
    assert _scan(c, 11, out).status_code == 200
    login(c, 11, 'late')
    checkin.became_student(con, departure)
    assert con.execute('SELECT done_at FROM qr_marks WHERE session_id = ? AND user_id = ?', (sid, departure)).fetchone()[0] is None
    assert _rows(c, sid)[0]['phase'] == 'out'
    c.post(f'/api/screens/{sid}/in', headers=tma(9))
    before = len(_rows(c, sid))
    old = int(p.split('_')[2]) * checkin.SLOT + checkin.SCAN_OK + 2 * checkin.SLOT
    monkeypatch.setattr(checkin.time, 'time', lambda: old)
    assert _scan(c, 10, p).status_code == 200  # completion retry, no new evidence
    assert len(_rows(c, sid)) == before
    con.close()


def test_unlinked_leaders_cannot_read_and_deleted_scans_disappear(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    sid, p = _start(c, oid, tags[0])
    assert _scan(c, 1, p).status_code == 200
    notice = _notice(con, sid, ids[8])
    for tg in (8, 9, 7):
        con.execute('DELETE FROM students WHERE user_id = ?', (ids[tg],))
        assert c.get(f'/api/screens/{sid}/scans', headers=tma(tg)).status_code == 403
        assert sid not in [s['session'] for s in c.get('/api/screens', headers=tma(tg)).json()]
    assert bot._render(con, notice) is None
    logic.account.delete_me(con, logic.Viewer(ids[1], 'user', True))
    assert not con.execute('SELECT 1 FROM qr_meet_scans WHERE user_id = ?', (ids[1],)).fetchone()
    assert not con.execute('SELECT 1 FROM qr_marks WHERE user_id = ?', (ids[1],)).fetchone()
    con.close()


def test_department_head_without_events_only_reviews_their_department(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    role = con.execute("""INSERT INTO org_roles (org_id, name, color, level, rights, created_at)
        VALUES (?, 'Department Head', 'blue', 'head', 'people', 0)""", (oid,)).lastrowid
    con.execute('UPDATE org_members SET role_id = ? WHERE org_id = ? AND user_id = ?', (role, oid, ids[8]))
    sid, p = _start(c, oid, tags[0])
    other, _ = _start(c, oid, tags[1])
    assert _scan(c, 1, p).status_code == 200
    shown = c.get(f'/api/screens/{sid}', headers=tma(8)).json()
    assert shown['reviewOnly'] and shown['param'] is None
    assert [s['session'] for s in c.get('/api/screens', headers=tma(8)).json()] == [sid]
    for path in ('', '/scans'):
        assert c.get(f'/api/screens/{other}{path}', headers=tma(8)).status_code == 403
    for action in ('start', 'finish', 'out', 'in', 'show', 'unpair', 'csv'):
        assert c.post(f'/api/screens/{sid}/{action}', headers=tma(8)).status_code == 403
    assert _rows(c, sid, 8)[0]['ask']
    assert c.post(f'/api/screens/{sid}/scans/{ids[1]}', headers=tma(8), json={'add': True}).status_code == 200
    con.execute('DELETE FROM member_tags WHERE tag_id = ? AND user_id = ?', (tags[0], ids[8]))
    assert c.get(f'/api/screens/{sid}/scans', headers=tma(8)).status_code == 403
    con.close()


def test_departure_only_retry_never_becomes_arrival(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    clock = [logic.now()]
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(checkin, 'now', lambda: clock[0])
    monkeypatch.setattr(checkin.time, 'time', lambda: clock[0])
    for tg, action in ((10, 'finish'), (11, 'in')):
        sid, p = _start(c, oid, tags[0])
        r = c.post(f'/api/screens/{sid}/out', headers=tma(9))
        assert r.status_code == 200
        p = r.json()['param']  # each phase has its own QR
        uid = c.get('/api/me', headers=tma(tg)).json()['id']
        assert _scan(c, tg, p).status_code == 200
        assert c.post(f'/api/screens/{sid}/{action}', headers=tma(9)).status_code == 200
        login(c, tg, f'late{tg}')
        checkin.became_student(con, uid)
        clock[0] += checkin.SCAN_OK + 2 * checkin.SLOT
        # a leaving QR retried once the door is back to arriving is refused (bound to its phase); after Finish it completes
        assert _scan(c, tg, p).status_code == (200 if action == 'finish' else 400)
        assert con.execute('SELECT done_at FROM qr_marks WHERE session_id = ? AND user_id = ?', (sid, uid)).fetchone()[0] is None
        assert [x['phase'] for x in _rows(c, sid)] == ['out']
    con.close()


def test_meetup_keeps_volunteer_door_runners_checkout(env, monkeypatch):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    monkeypatch.setattr(logic.vol, 'ORG', 'chess')
    sid, p = _start(c, oid, 'club')
    assert _scan(c, 2, p).status_code == 200
    assert not con.execute('SELECT 1 FROM qr_marks WHERE session_id = ? AND user_id = ?', (sid, ids[9])).fetchone()
    shift = con.execute('SELECT h.id FROM vol_shifts h JOIN vol_people v ON v.id = h.vol_id WHERE h.session_id = ? AND v.user_id = ?', (sid, ids[9])).fetchone()
    assert shift
    r = c.post(f'/api/screens/{sid}/out', headers=tma(9))
    assert r.status_code == 200
    p = r.json()['param']  # each phase has its own QR
    assert _scan(c, 9, p).status_code == 200
    assert con.execute('SELECT out_at FROM vol_shifts WHERE id = ?', (shift[0],)).fetchone()[0] is not None
    assert _scan(c, 4, p).status_code == 200  # departure-only evidence never invents a volunteer shift
    assert not con.execute('SELECT 1 FROM vol_people WHERE user_id = ?', (ids[4],)).fetchone()
    con.close()


def test_concurrent_scans_queue_one_push_and_two_departments_cannot_claim_one_member(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    other_head = _join(c, con, oid, 6, 'otherhead', 'head')
    con.execute('INSERT INTO member_tags (tag_id, user_id) VALUES (?, ?)', (tags[1], other_head))
    sid, p = _start(c, oid, tags[0])
    second, q = _start(c, oid, tags[1])
    scans = []
    ts = [threading.Thread(target=lambda: scans.append(_scan(c, 1, p).status_code)) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert scans == [200] * 4
    assert con.execute("SELECT COUNT(*) FROM bot_outbox WHERE kind = 'meetup_review' AND ref = ?", (f'meet:{sid}',)).fetchone()[0] == 1
    assert _scan(c, 1, q).status_code == 200
    results = []
    def decide(session, tg):
        results.append(c.post(f'/api/screens/{session}/scans/{ids[1]}', headers=tma(tg), json={'add': True}).status_code)
    ts = [threading.Thread(target=decide, args=(sid, 8)), threading.Thread(target=decide, args=(second, 6))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(results) == [200, 409]
    assert con.execute('SELECT COUNT(*) FROM member_tags WHERE user_id = ?', (ids[1],)).fetchone()[0] == 1
    con.close()


def test_one_person_replaying_a_fresh_qr_is_capped(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    oid, tags, ids = _setup(c, con)
    sid, p = _start(c, oid, tags[0])
    for _ in range(checkin.MEET_SCANS + 5):
        assert _scan(c, 4, p).status_code == 200  # the scan still answers; only the evidence stops growing
    assert _scan(c, 2, p).status_code == 200
    n = dict(con.execute('SELECT user_id, COUNT(*) FROM qr_meet_scans WHERE session_id = ? GROUP BY user_id', (sid,)).fetchall())
    assert n == {ids[4]: checkin.MEET_SCANS, ids[2]: 1}
    con.close()
