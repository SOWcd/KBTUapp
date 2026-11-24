"""The event editor's two newer rules (logic/organizing.py): a cover per format (the Feed's tall slide, the event's
card, a list's thumbnail: its own crop or its own photo over the one cover), and a member's draft that the club's
President or a Vice approves."""
from __future__ import annotations

import io

from PIL import Image

from kbtu import bot, db, logic, texts
from test_core import env, login, tma  # noqa: F401  (env is a fixture)

PRES, VICE, HEAD, MEMBER, OUTSIDER, OTHER_VICE = 20, 21, 22, 23, 30, 31
EV = {"place": "Atrium", "emoji": "crown_3d", "color": "#3B6BFF", "seats": None, "title": "Quiz night"}


def _club(c, cfg):
    """Crystal: President 20, Vice 21, Head 22, Member 23; 30 is in no club, 31 is another club's Vice."""
    for tg, name in ((PRES, "pres"), (VICE, "vice"), (HEAD, "head"), (MEMBER, "memb"), (OUTSIDER, "out"), (OTHER_VICE, "other")):
        login(c, tg, name)
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    org = logic.create_org(con, None, "Crystal", "CR", "crown_3d", True)
    for tg, role in ((PRES, "president"), (VICE, "vice"), (HEAD, "head"), (MEMBER, "member")):
        logic.set_role(con, None, uid(tg), org, role, "test")
    logic.set_role(con, None, uid(OTHER_VICE), logic.create_org(con, None, "JCC", "JC", "crown_3d", True), "vice", "test")
    return con, org, uid


def _photo(c, tg, shade):
    raw = io.BytesIO()
    Image.new("RGB", (900, 600), (shade, 40, 200 - shade)).save(raw, "JPEG")
    r = c.post("/api/photos", headers=tma(tg), content=raw.getvalue())
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _draft(c, org, tg=PRES, **kw):
    r = c.post(f"/api/orgs/{org}/events", headers=tma(tg), json={**EV, "startsAt": logic.core.now() + 86400, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_cover_per_format(env):
    c, cfg = env
    con, org, _ = _club(c, cfg)
    cover, tall, theirs = _photo(c, PRES, 10), _photo(c, PRES, 90), _photo(c, HEAD, 170)
    # created with one photo, the Feed's own crop and the list's own photo
    e = _draft(c, org, coverId=cover, coverFocus=[0.5, 0.2], coverFormats={"feed": {"focus": [0.1, 0.9]}, "list": {"id": tall, "focus": None}})
    eid, got = e["id"], e["cover"]
    assert got["id"] == cover and got["focus"] == [0.5, 0.2]
    assert got["formats"]["feed"] == {"focus": [0.1, 0.9]}                       # a crop: no photo of its own
    assert got["formats"]["list"]["id"] == tall and got["formats"]["list"]["url"].endswith(".webp") and got["formats"]["list"]["focus"] is None
    assert "card" not in got["formats"]
    # the same in Studio's list (read once for all rows) and on the event's page
    assert c.get(f"/api/orgs/{org}/events", headers=tma(PRES)).json()[0]["cover"]["formats"] == got["formats"]
    assert c.get(f"/api/events/{eid}", headers=tma(HEAD)).json()["cover"]["formats"] == got["formats"]
    patch = lambda body, tg=PRES: c.patch(f"/api/events/{eid}", headers=tma(tg), json={**EV, "startsAt": logic.core.now() + 86400, **body})  # noqa: E731
    # left out: kept; one format changed: the others stay; null: back to the cover
    assert patch({}).json()["cover"]["formats"] == got["formats"]
    by = patch({"coverFormats": {"card": {"focus": [1, 0]}, "feed": None}}).json()["cover"]["formats"]
    assert set(by) == {"card", "list"} and by["card"] == {"focus": [1.0, 0.0]}
    # a photo that is neither mine nor on that format already, the cover itself, a wrong format or point: refused
    for bad in ({"feed": {"id": theirs}}, {"feed": {"id": cover}}, {"feed": {"id": 10 ** 9}}, {"story": {"focus": [0, 0]}},
                {"feed": {"focus": [2, 0]}}, {"feed": "x"}, ["feed"]):
        assert patch({"coverFormats": bad}).status_code == 400, bad
    # a co-organizer keeps my photo on its format (it is the event's already), and puts their own on another
    by = patch({"coverFormats": {"list": {"id": tall, "focus": [0.3, 0.3]}, "feed": {"id": theirs}}}, HEAD).json()["cover"]["formats"]
    assert by["list"]["id"] == tall and by["list"]["focus"] == [0.3, 0.3] and by["feed"]["id"] == theirs
    assert patch({"coverFormats": {"card": {"id": tall}}}, HEAD).status_code == 400      # but not onto a format it isn't on
    assert patch({"coverFormats": {"feed": {"focus": [0, 0]}}}, MEMBER).status_code == 403  # nor may a plain member touch the club's event
    # a photo in use is never trimmed away as an unused upload
    assert con.execute(logic.account._FILE_USED.format(fid=tall)).fetchone()
    # another cover and nothing said: the crops made for the old photo go, a format's own photo stays
    patch({"coverFormats": {"card": {"focus": [0.2, 0.2]}}})
    by = patch({"coverId": _photo(c, PRES, 130)}).json()["cover"]["formats"]
    assert set(by) == {"list", "feed"}
    # no cover: none of them; and the event's deletion takes its rows
    assert patch({"coverId": None}).json()["cover"] is None
    assert con.execute("SELECT COUNT(*) FROM event_covers").fetchone()[0] == 0
    patch({"coverId": cover, "coverFormats": {"list": {"id": tall}}})
    assert c.delete(f"/api/events/{eid}", headers=tma(PRES)).status_code == 204
    assert con.execute("SELECT COUNT(*) FROM event_covers").fetchone()[0] == 0


def test_a_member_drafts_the_club_approves(env):
    c, cfg = env
    con, org, uid = _club(c, cfg)
    assert c.post(f"/api/orgs/{org}/events", headers=tma(OUTSIDER), json={**EV, "startsAt": logic.core.now() + 86400}).status_code == 403
    e = _draft(c, org, MEMBER, coverId=_photo(c, MEMBER, 50))               # a member uploads a cover and makes a draft
    eid = e["id"]
    assert e["status"] == "draft" and e["review"] == {"mine": True, "askedAt": None, "reason": None}
    assert c.post(f"/api/events/{eid}/publish", headers=tma(MEMBER)).status_code == 403   # never publishes it
    assert c.post(f"/api/events/{eid}/review", headers=tma(VICE), json={"ok": True}).status_code == 409  # nothing asked yet
    assert c.post(f"/api/events/{eid}/submit", headers=tma(HEAD)).status_code == 409      # only its author sends it
    # sent: the President and the Vice hear it from the bot (a template, a button into Studio), nobody else
    r = c.post(f"/api/events/{eid}/submit", headers=tma(MEMBER))
    assert r.status_code == 200 and r.json()["review"]["askedAt"]
    told = con.execute("SELECT * FROM bot_outbox WHERE kind = 'event_review' ORDER BY user_id").fetchall()
    assert sorted(m["user_id"] for m in told) == sorted([uid(PRES), uid(VICE)])
    text, button, start = bot._render(con, {**dict(told[0]), "lang": "en"})
    assert (text, button) == texts.bot_message("en", "event_review", org="Crystal") and start == f"st_{org}" and "Quiz" not in text
    # Studio shows it to them with where it stands; the author still edits it
    row = next(x for x in c.get(f"/api/orgs/{org}/events", headers=tma(VICE)).json() if x["id"] == eid)
    assert row["review"]["mine"] is False and row["review"]["askedAt"]
    edit = lambda tg, title: c.patch(f"/api/events/{eid}", headers=tma(tg), json={**EV, "title": title, "startsAt": logic.core.now() + 86400})  # noqa: E731
    assert edit(MEMBER, "Quiz night 2").json()["title"] == "Quiz night 2"
    # the answer is the club's President's or a Vice's alone
    for tg in (MEMBER, HEAD, OUTSIDER, OTHER_VICE):
        assert c.post(f"/api/events/{eid}/review", headers=tma(tg), json={"ok": True}).status_code == 403, tg
    # returned with a reason from the list (never typed words); the author hears it, fixes it and sends it again
    assert c.post(f"/api/events/{eid}/review", headers=tma(VICE), json={"ok": False, "reason": "because"}).status_code == 400
    back = c.post(f"/api/events/{eid}/review", headers=tma(VICE), json={"ok": False, "reason": "when"}).json()
    assert back["status"] == "draft" and back["review"]["askedAt"] is None and back["review"]["reason"] == "when"
    assert bot._render(con, {**dict(told[0]), "lang": "en"}) is None        # the ask is answered: its message is quiet
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'event_returned'").fetchone()
    assert m["user_id"] == uid(MEMBER) and bot._render(con, {**dict(m), "lang": "en"})[2] == f"st_{org}"
    assert c.get(f"/api/events/{eid}", headers=tma(MEMBER)).json()["review"]["reason"] == "when"
    assert c.post(f"/api/events/{eid}/review", headers=tma(PRES), json={"ok": True}).status_code == 409   # not waiting any more
    again = c.post(f"/api/events/{eid}/submit", headers=tma(MEMBER)).json()["review"]
    assert again["askedAt"] and again["reason"] is None
    # approved: published as the Vice's own Publish would; the author hears it and can't edit it any more
    out = c.post(f"/api/events/{eid}/review", headers=tma(VICE), json={"ok": True})
    assert out.status_code == 200 and out.json()["status"] == "published" and "review" not in out.json()
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'event_approved'").fetchone()
    assert m["user_id"] == uid(MEMBER) and bot._render(con, {**dict(m), "lang": "ru"})[2] == f"ev_{eid}"
    assert con.execute("SELECT COUNT(*) FROM event_reviews").fetchone()[0] == 0
    assert edit(MEMBER, "Mine again").status_code == 403
    assert c.delete(f"/api/events/{eid}", headers=tma(MEMBER)).status_code == 403
    assert edit(HEAD, "Quiz night 3").json()["title"] == "Quiz night 3"     # the "events" right edits it from here on


def test_a_members_own_draft_only(env):
    c, cfg = env
    con, org, _ = _club(c, cfg)
    theirs = _draft(c, org, PRES)["id"]
    body = {**EV, "startsAt": logic.core.now() + 86400}
    assert c.patch(f"/api/events/{theirs}", headers=tma(MEMBER), json=body).status_code == 403   # not another's draft
    assert c.post(f"/api/events/{theirs}/submit", headers=tma(PRES)).status_code == 409           # an organizer publishes theirs
    mine = _draft(c, org, MEMBER)["id"]
    assert c.delete(f"/api/events/{mine}", headers=tma(MEMBER)).status_code == 204                # their own draft goes
    for _ in range(logic.organizing.DRAFTS_A_DAY):
        _draft(c, org, MEMBER)
    r = c.post(f"/api/orgs/{org}/events", headers=tma(MEMBER), json=body)
    assert r.status_code == 429 and r.json()["message"] == "drafts"                               # a day's cap, the organizers have none
    for _ in range(2):
        _draft(c, org, PRES)
