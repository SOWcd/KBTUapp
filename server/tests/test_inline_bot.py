"""Inline mode (bot.inline_answer): a student's friend card, a live team link per club they may share, the afisha's
public events searched by title; never a draft, hidden, members-only or initiative-only event; a stranger gets one button."""
from __future__ import annotations

from kbtu import bot, db, logic
from test_afisha import EV, INIT, MEMBER, OFF, OTHER, _event, _setup
from test_core import env, tma  # noqa: F401  (env is a fixture)


def _ask(cfg, tg, query=""):
    con = db.connect(cfg.db_path)
    try:
        return bot.inline_answer(cfg, con, {"id": "q1", "from": {"id": tg, "language_code": "en"}, "query": query})
    finally:
        con.close()


def _ids(body):
    return [r["id"] for r in body["results"]]


def test_inline_answer(env):
    c, cfg = env
    con, init, off = _setup(c, cfg)
    public = _event(c, off, OFF, "Hackathon Night")
    other = _event(c, off, OFF, "Chess Cup")
    initiative = _event(c, init, INIT, "Hackathon Secret")  # an initiative's: off the general afisha
    members = _event(c, off, OFF, "Hackathon Members")
    con.execute("UPDATE events SET visibility = 'members' WHERE id = ?", (members,))
    hidden = _event(c, off, OFF, "Hackathon Hidden")
    con.execute("UPDATE events SET hidden_at = 1 WHERE id = ?", (hidden,))
    draft = c.post(f"/api/orgs/{off}/events", headers=tma(OFF), json={**EV, "title": "Hackathon Draft", "startsAt": logic.now() + 86400}).json()["id"]
    leak = {f"ev-{x}" for x in (initiative, members, hidden, draft)}

    # an unknown person: no cards, one button into the app
    body = _ask(cfg, 999)
    assert body["results"] == [] and body["button"]["web_app"]["url"].startswith("https://") and body["is_personal"]

    # empty query, a plain student: my friend card and the next events, no club card
    body = _ask(cfg, OTHER)
    ids = _ids(body)
    assert ids[0] == "rf" and not any(i.startswith("jm-") for i in ids) and {f"ev-{public}", f"ev-{other}"} <= set(ids)
    assert not leak & set(ids)
    rf = body["results"][0]["reply_markup"]["inline_keyboard"][0][0]["url"]
    assert "startapp=r_" in rf and str(OTHER) not in rf.split("=")[1]

    # a President: no club card until the team link is live (typing never makes one), then one card with it
    assert not any(i.startswith("jm-") for i in _ids(_ask(cfg, OFF)))
    token = c.post(f"/api/orgs/{off}/team-link", headers=tma(OFF)).json()["token"]
    jm = [r for r in _ask(cfg, OFF)["results"] if r["id"] == f"jm-{off}"]
    assert jm and jm[0]["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(f"startapp=join_{off}_{token}")
    assert not any(i.startswith("jm-") for i in _ids(_ask(cfg, MEMBER)))  # a member may not share it

    # a typed query: matching public events only, no personal cards
    ids = _ids(_ask(cfg, MEMBER, "hackath"))
    assert ids == [f"ev-{public}"]
    assert "startapp=ev_" in _ask(cfg, OTHER, "chess")["results"][0]["reply_markup"]["inline_keyboard"][0][0]["url"]
