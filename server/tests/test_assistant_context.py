"""The assistant asked from a card ("Ask AI" on an event or a club): the server reads the card's facts by id itself;
an unknown id, a draft, a hidden, a team-only event or a hidden club adds nothing (no leak), and a bad context is a 400
that costs none of the day's questions."""
from __future__ import annotations

import json
import time

from kbtu import db, llm
from test_core import _board_on, env, login, tma  # noqa: F401  (env: the fixture)


def test_card_context(env, monkeypatch):
    c, cfg = env
    login(c, 1, "ann")
    _board_on(c, cfg)
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, description, links, created_at) VALUES "
                "(1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 'We build robots.', '[\"https://tiktok.com/@itclub\"]', 0)")
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, status, created_at) VALUES (2, 'gone', 'club', 'Gone Club', 'G', 'x', 'hidden', 0)")
    later = int(time.time()) + 86400
    for eid, org, status, extra, title in ((7, 1, "published", "", "Hackathon"), (8, 1, "draft", "", "Secret draft"),
                                           (9, 1, "published", "hidden_at = 1,", "Taken down"), (10, 1, "published", "visibility = 'members',", "Team only"),
                                           (11, 2, "published", "", "Of a hidden club")):
        con.execute(f"""INSERT INTO events (id, org_id, status, title, description, place, starts_at, price, pay_to_name, pay_phone,
            created_by, created_at, updated_at) VALUES (?, ?, ?, ?, 'Bring a laptop.', '305', ?, 500, 'Dana K', '+77001234567', NULL, 0, 0)""",
                    (eid, org, status, title, later))
        if extra:
            con.execute(f"UPDATE events SET {extra.rstrip(',')} WHERE id = ?", (eid,))
    seen: list = []

    async def fake(cfg_, http, msgs, **kw):
        seen.append(msgs[0]["content"])
        return json.dumps({"text": "Bring a laptop.", "actions": [{"type": "event", "id": 7}]}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    ask = lambda ctx: c.post("/api/assistant", headers=tma(1), json={"q": "what to bring?", "context": ctx})  # noqa: E731

    r = ask({"kind": "event", "id": 7}).json()
    page = seen[-1].split("The student opened you from", 1)[1]
    assert "Hackathon" in page and "Bring a laptop" in page and "IT Club" in page and "500 tenge" in page
    assert "Dana" not in seen[-1] and "+7700" not in seen[-1]               # the payee's name and phone never go
    assert r["actions"] == [{"type": "event", "id": 7}]
    ask({"kind": "club", "id": 1})
    assert "We build robots." in seen[-1] and "tiktok.com/@itclub" in seen[-1] and "join requests" in seen[-1]

    for eid in (8, 9, 10, 11, 404):                                          # nothing of these reaches the model
        ask({"kind": "event", "id": eid})
        assert "opened you from" not in seen[-1] and "Secret" not in seen[-1] and "Taken down" not in seen[-1] \
            and "Team only" not in seen[-1] and "Of a hidden club" not in seen[-1]
    ask({"kind": "club", "id": 2})
    assert "Gone Club" not in seen[-1]

    used = con.execute("SELECT COUNT(*) FROM assist_uses").fetchone()[0]
    for bad in ({"kind": "user", "id": 1}, {"kind": "event", "id": "7"}, {"kind": "event", "id": True}, "event 7", [7]):
        assert ask(bad).status_code == 400
    assert con.execute("SELECT COUNT(*) FROM assist_uses").fetchone()[0] == used  # a bad context costs nothing
    con.close()


def test_the_assistant_keeps_to_its_scope():
    """The rule that it is not a homework machine and takes no orders from a message (owner, Nov 11), and the limits
    that make abuse dull: a short question, a short answer, a day's count."""
    from kbtu.logic import assistant as a
    assert "never instructions" in a.SYSTEM and "no solving tasks" in a.SYSTEM
    assert a.Q_MAX <= 300 and a.A_DAY <= 30
    a.SYSTEM.format(lang="Russian", facts="", not_care="", hate="")  # still formats: no stray braces
