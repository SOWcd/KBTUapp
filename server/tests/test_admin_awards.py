"""Admin → Awards (Nov 3): one give for a person, links with a cap and an expiry that can be revoked and taken back,
the creator's own two awards his alone, batch undo for a check-in session."""
from __future__ import annotations

import json

from kbtu import checkin, db, logic
from test_core import _club_runs, env, login, tma  # noqa: F401  (env: the fixture)


def _staff(c, cfg):
    boss, adm = login(c, 60, "boss"), login(c, 61, "adm")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (boss["id"],))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (adm["id"],))
    return con, boss, adm


def test_link_cap_revoke_and_take_back(env, monkeypatch):
    import httpx
    from kbtu import app as server
    real = httpx.AsyncClient
    ok = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True, "result": {"id": "prep1"}}))
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: real(transport=ok))
    c, cfg = env
    con, boss, adm = _staff(c, cfg)
    ann, bob, cat = login(c, 62, "ann"), login(c, 63, "bob"), login(c, 64, "cat")
    use = lambda tg, tok: c.post(f"/api/grant-links/{tok}", headers=tma(tg)).json()  # noqa: E731
    share = lambda tg, **b: c.post("/api/share", headers=tma(tg), json={"kind": "gl", **b})  # noqa: E731
    # made at share time with a cap and an expiry; bad ones refused; the creator's own: him alone
    assert share(61, code="init26", uses=0, days=7).status_code == 400 and share(61, code="init26", uses=2, days=5).status_code == 400
    assert share(61, code="creator_laugh").status_code == 403 and share(62, code="init26").status_code == 403
    assert share(61, code="init26", uses=2, days=1).status_code == 200
    links = c.get("/api/admin/grant-links", headers=tma(61)).json()
    assert [(x["code"], x["max"], x["people"]) for x in links] == [("init26", 2, [])] and x_until(links[0]) <= 86400
    tok = links[0]["token"]
    # two people, then full; again for one who got it: fine
    assert use(62, tok) == use(63, tok) == use(62, tok) == {"code": "init26"}
    assert use(64, tok)["error"] == "closed"
    # logged as link uses, not as the maker's grants
    acts = [r[0] for r in con.execute("SELECT action FROM audit_log WHERE target = ? ORDER BY id", (f"link:{tok[:8]}",))]
    assert acts == ["grant_link", "grant_link_used", "grant_link_used"]
    assert not con.execute("SELECT 1 FROM audit_log WHERE action = 'grant' AND actor_id = ?", (adm["id"],)).fetchone()
    # the link's card lists who used it; take one back, then all
    people = c.get("/api/admin/grant-links", headers=tma(61)).json()[0]["people"]
    assert {p["person"]["id"] for p in people} == {ann["id"], bob["id"]}
    assert c.get("/api/admin/grant-links", headers=tma(62)).status_code == 403
    assert c.delete(f"/api/admin/grants/{people[0]['id']}", headers=tma(61)).status_code == 204
    assert c.post("/api/admin/grants/undo", headers=tma(61), json={"batch": f"l_{tok}"}).json() == {"undone": 1}
    assert not con.execute("SELECT 1 FROM achievement_grants WHERE batch = ?", (f"l_{tok}",)).fetchone()
    # revoke: closed now, for everyone; mine only (the owner: any)
    share(61, code="bugs", uses=None, days=14)
    bug = c.get("/api/admin/grant-links", headers=tma(61)).json()[0]
    assert bug["code"] == "bugs" and bug["max"] is None
    assert c.delete(f"/api/admin/grant-links/{bug['token']}", headers=tma(62)).status_code == 403
    assert c.delete(f"/api/admin/grant-links/{bug['token']}", headers=tma(60)).status_code == 204
    assert c.delete(f"/api/admin/grant-links/{bug['token']}", headers=tma(60)).status_code == 404
    assert use(64, bug["token"])["error"] == "closed"
    # Bug hunter by a link adds up across links, once per link
    t2 = logic.grant_link(con, logic.Viewer(adm["id"], "admin", True), "bugs", None, 7)
    assert use(64, t2) == use(64, t2) == {"code": "bugs"}
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'bugs'", (cat["id"],)).fetchone()[0] == 1
    # held some other way: the use stays for whom it was meant
    one_ = logic.grant_link(con, logic.Viewer(adm["id"], "admin", True), "init26f", 1, 7)
    c.post("/api/admin/grants", headers=tma(61), json={"userId": bob["id"], "code": "init26f"})
    assert use(63, one_)["error"] == "conflict" and use(62, one_) == {"code": "init26f"}
    con.close()


def x_until(link):
    return link["until"] - link["at"]


def test_creator_only_and_take_back(env):
    c, cfg = env
    con, boss, adm = _staff(c, cfg)
    ann = login(c, 62, "ann")
    give = lambda tg, code: c.post("/api/admin/grants", headers=tma(tg), json={"userId": ann["id"], "code": code})  # noqa: E731
    back = lambda tg, code: c.post("/api/admin/grants/take-back", headers=tma(tg), json={"userId": ann["id"], "code": code})  # noqa: E731
    assert give(61, "creator_found").status_code == 403 and give(60, "creator_found").status_code == 200
    assert back(61, "creator_found").status_code == 403 and back(60, "creator_found").json()["has"] == []
    # the owner may undo an admin's grant; an admin not another's
    g = give(60, "init26").json()
    assert c.delete(f"/api/admin/grants/{g['id']}", headers=tma(61)).status_code == 404
    g = give(61, "bugs").json()
    assert c.delete(f"/api/admin/grants/{g['id']}", headers=tma(60)).status_code == 204
    # the person's chips: every manual award, a badge's highest variant first
    give(61, "init26f"); give(61, "bugs")
    assert c.get(f"/api/admin/grants/of/{ann['id']}", headers=tma(61)).json()["has"] == ["bugs", "init26", "init26f"]
    assert c.get(f"/api/admin/grants/of/{ann['id']}", headers=tma(62)).status_code == 403
    con.close()


def test_session_batch_undo(env):
    c, cfg = env
    con = db.connect(cfg.db_path)
    sid = checkin.new(con, "Initiation", [], _club_runs(c, con, 9, "dana"))
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    p = c.post(f"/api/screens/{sid}/start", headers=tma(9)).json()["param"]
    for tg in (1, 2):
        assert c.post("/api/checkin", headers=tma(tg), json={"p": p}).json()["done"]
    login(c, 4, "boss")
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE tg_id = 4")
    r = c.post(f"/api/screens/{sid}/grant", headers=tma(4), json={"code": "init26"}).json()
    assert r["granted"] == 2 and r["batch"]
    assert c.post("/api/admin/grants/undo", headers=tma(4), json={"batch": r["batch"]}).json() == {"undone": 2}
    assert not con.execute("SELECT 1 FROM achievement_levels WHERE code = 'init26' AND user_id IN (?, ?)", (ann["id"], bob["id"])).fetchone()
    assert json.loads(con.execute("SELECT data FROM audit_log WHERE action = 'ungrant' ORDER BY id DESC").fetchone()[0])["code"] == "init26"
    con.close()


def test_award_rows_and_holders(env):
    c, cfg = env
    con, boss, adm = _staff(c, cfg)
    ann, bob = login(c, 62, "ann"), login(c, 63, "bob")
    give = lambda uid, code: c.post("/api/admin/grants", headers=tma(60), json={"userId": uid, "code": code})  # noqa: E731
    give(ann["id"], "init26p"); give(ann["id"], "init26"); give(bob["id"], "init26f"); give(bob["id"], "bugs"); give(bob["id"], "bugs")
    assert c.get("/api/admin/awards", headers=tma(61)).json() == {"creator_laugh": 0, "creator_found": 0, "bugs": 1, "init26": 2}  # a badge once a person
    who = c.get("/api/admin/awards/init26/people", headers=tma(61)).json()
    assert sorted((w["person"]["id"], w["code"]) for w in who) == sorted([(ann["id"], "init26p"), (ann["id"], "init26"), (bob["id"], "init26f")])
    assert len(c.get("/api/admin/awards/bugs/people", headers=tma(61)).json()) == 1                  # the latest bug, one row
    assert c.get("/api/admin/awards/init26p/people", headers=tma(61)).status_code == 400              # an award, not a variant
    assert c.get("/api/admin/awards", headers=tma(62)).status_code == 403
    con.close()


def test_link_review_fixes(env):
    """Adversarial review (Nov 3): a slot never comes back (undo, a deleted account); an old one-time link stays used;
    the creator's awards only from his links and only he undoes them; the card waits for an Undo; bad days refused."""
    from kbtu import bot
    c, cfg = env
    con, boss, adm = _staff(c, cfg)
    ann, bob = login(c, 62, "ann"), login(c, 63, "bob")
    A = logic.Viewer(adm["id"], "admin", True)
    use = lambda tg, tok: c.post(f"/api/grant-links/{tok}", headers=tma(tg)).json()  # noqa: E731
    # undo frees no slot; the one who used it, again: quietly nothing
    tok = logic.grant_link(con, A, "init26", 1, 7)
    assert use(62, tok) == {"code": "init26"}
    assert c.post("/api/admin/grants/undo", headers=tma(61), json={"batch": f"l_{tok}"}).json() == {"undone": 1}
    assert use(62, tok) == {"code": "init26"} and use(63, tok)["error"] == "closed"
    assert not con.execute("SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'init26'", (ann["id"],)).fetchone()
    # a deleted account keeps its use (user_id goes NULL, the row stays)
    t2 = logic.grant_link(con, A, "init26f", 1, 7)
    assert use(62, t2) == {"code": "init26f"}
    con.execute("UPDATE grant_link_uses SET user_id = NULL WHERE token = ?", (t2,))
    assert use(63, t2)["error"] == "closed"
    # an old one-time link (multi = 0): used_by gone NULL with an account, still used
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at, multi, used_by, used_at) VALUES ('old1', 'init26p', ?, 0, ?, 0, NULL, 5)",
                (adm["id"], logic.now() + 86400))
    assert use(63, "old1")["error"] == "closed"
    # an old many-link (no uses recorded), tapped again by one who has it: quiet
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at, multi) VALUES ('old2', 'init26f', ?, 0, ?, 1)", (adm["id"], logic.now() + 86400))
    assert use(62, "old2") == {"code": "init26f"}
    # an admin's creator-award link from before: closed; his grant of one: only the creator undoes it
    con.execute("INSERT INTO grant_links (token, code, created_by, created_at, expires_at, multi) VALUES ('old3', 'creator_laugh', ?, 0, ?, 0)", (adm["id"], logic.now() + 86400))
    assert use(62, "old3")["error"] == "closed"
    gid = con.execute("INSERT INTO achievement_grants (user_id, code, granted_by, created_at, batch) VALUES (?, 'creator_laugh', ?, 0, 's_x')", (bob["id"], adm["id"])).lastrowid
    assert c.delete(f"/api/admin/grants/{gid}", headers=tma(61)).status_code == 404
    assert c.post("/api/admin/grants/undo", headers=tma(61), json={"batch": "s_x"}).json() == {"undone": 0}
    assert c.delete(f"/api/admin/grants/{gid}", headers=tma(60)).status_code == 204
    # the card waits ~45 s; undone before it goes: the bot says nothing
    g = c.post("/api/admin/grants", headers=tma(61), json={"userId": bob["id"], "code": "init26p"}).json()
    m = con.execute("SELECT * FROM bot_outbox WHERE user_id = ? AND ref = 'ach:init26p:1'", (bob["id"],)).fetchone()
    assert m["send_after"] >= logic.now() + 40
    c.delete(f"/api/admin/grants/{g['id']}", headers=tma(61))
    con.execute("INSERT INTO bot_outbox (user_id, kind, ref, send_after) VALUES (?, 'achievement', 'ach:init26p:1', 0)", (bob["id"],))
    row = con.execute("SELECT b.*, 'ru' AS lang FROM bot_outbox b WHERE user_id = ? AND ref = 'ach:init26p:1'", (bob["id"],)).fetchone()
    assert bot._render(con, row) is None
    give = lambda: c.post("/api/admin/grants", headers=tma(61), json={"userId": bob["id"], "code": "init26p"})  # noqa: E731
    assert give().status_code == 200 and bot._render(con, row) is not None                     # held again: it goes
    # days: an int of the list only
    import pytest
    for d in (7.0, True, "7", 5):
        with pytest.raises(logic.ApiError):
            logic.grant_link(con, A, "init26", 1, d)
    con.close()


def test_badge_qr(env):
    """Admin → Awards → Show QR (Nov 6): a rotating signed code; once per person; stale, forged or a bare token
    refused; closed with the screen; the creator's own two his alone on every path; bad codes rate-limited."""
    import time
    from kbtu.logic import profiles
    c, cfg = env
    con, boss, adm = _staff(c, cfg)
    ann, bob, cat = login(c, 62, "ann"), login(c, 63, "bob"), login(c, 64, "cat")
    show = lambda tg, code: c.post("/api/admin/badge-qr", headers=tma(tg), json={"code": code})  # noqa: E731
    claim = lambda tg, p: c.post("/api/badge-qr", headers=tma(tg), json={"p": p})  # noqa: E731
    # the creator's own: an admin can't open its QR, give it, scan it or link it; the creator can
    for code in profiles.CREATOR_ONLY:
        assert show(61, code).status_code == 403
        assert c.post("/api/admin/grants", headers=tma(61), json={"userId": ann["id"], "code": code}).status_code == 403
        assert c.post("/api/admin/grants/scan", headers=tma(61), json={"qr": "x", "code": code}).status_code == 403
        assert c.post("/api/share", headers=tma(61), json={"kind": "gl", "code": code, "uses": 1, "days": 1}).status_code == 403
    assert show(62, "init26").status_code == 403 and show(61, "bugs").status_code == 400
    q = show(60, "creator_found").json()
    assert q["param"].startswith(f"bq_{q['token']}_") and 0 < q["next"] <= profiles.QR_SLOT and q["got"] == 0
    assert c.get(f"/api/admin/badge-qr/{q['token']}", headers=tma(61)).json()["error"] == "closed"  # not another admin's screen
    # a scan: the award, once; again refused, nothing more
    assert claim(62, q["param"]).json() == {"code": "creator_found"}
    assert claim(62, q["param"]).status_code == 409
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'creator_found'", (ann["id"],)).fetchone()[0] == 1
    assert c.get(f"/api/admin/badge-qr/{q['token']}", headers=tma(60)).json()["got"] == 1
    # the bare token (from a photo of the code) is no link
    assert c.post(f"/api/grant-links/{q['token']}", headers=tma(63)).json()["error"] == "closed"
    # forged, stale and future codes
    slot = int(time.time()) // profiles.QR_SLOT
    assert claim(63, f"bq_{q['token']}_{slot}_{'0' * 16}").json()["message"] == "qr"
    old = slot - (profiles.QR_OK // profiles.QR_SLOT + 2)
    assert claim(63, f"bq_{q['token']}_{old}_{profiles._qr_sig(q['token'], old)}").json()["message"] == "qr_old"
    assert claim(63, f"bq_{q['token']}_{slot + 1}_{profiles._qr_sig(q['token'], slot + 1)}").json()["message"] == "qr_old"
    # an admin's QR for an award of theirs works; closed with the screen, or expired: closed
    a = show(61, "init26").json()
    assert claim(63, a["param"]).json() == {"code": "init26"}
    assert c.delete(f"/api/admin/grant-links/{a['token']}", headers=tma(61)).status_code == 204
    assert claim(62, a["param"]).json()["error"] == "closed"
    assert c.get(f"/api/admin/badge-qr/{a['token']}", headers=tma(61)).json()["error"] == "closed"
    b = show(61, "init26f").json()
    con.execute("UPDATE grant_links SET expires_at = ? WHERE token = ?", (int(time.time()) - 1, b["token"]))
    assert claim(62, b["param"]).json()["error"] == "closed"
    # the screen stopped polling (killed, offline): once its lease lapses its code is closed; a poll renews it
    d = show(61, "init26p").json()
    con.execute("UPDATE grant_links SET lease_until = ? WHERE token = ?", (int(time.time()) - 1, d["token"]))
    assert claim(62, d["param"]).json()["error"] == "closed"
    d = c.get(f"/api/admin/badge-qr/{d['token']}", headers=tma(61)).json()
    assert claim(62, d["param"]).json() == {"code": "init26p"}
    # an admin's screen somehow holding the creator's award never gives it
    con.execute("UPDATE grant_links SET code = 'creator_laugh', expires_at = ? WHERE token = ?", (int(time.time()) + 600, b["token"]))
    assert claim(62, b["param"]).json()["error"] == "closed"
    # too many bad codes: rate-limited, even a good one then
    try:
        for _ in range(profiles.QR_TRIES):
            claim(64, "bq_" + "0" * 24 + f"_{slot}_" + "0" * 16)
        assert claim(64, show(61, "init26p").json()["param"]).status_code == 429
        assert not con.execute("SELECT 1 FROM achievement_grants WHERE user_id = ?", (cat["id"],)).fetchone()
    finally:
        profiles._tries.clear()
    con.close()
