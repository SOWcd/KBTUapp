"""A room's place in the assistant's answer comes only from the map's room list (Nov 19: "404 is on floor 4, in
Independence hall's wing", "67 is in the basement", both guessed from the digits): a room on the map gets its floor and
a map button; a number the map doesn't have is "unknown", never a floor, and its button opens nothing."""
from __future__ import annotations

import json

from kbtu import llm
from kbtu.logic import assistant
from test_core import _board_on, env, login, tma  # noqa: F401  (env: the fixture)


def test_a_rooms_place_only_from_the_map(env, monkeypatch):
    c, cfg = env
    login(c, 1, "ann")
    _board_on(c, cfg)
    seen: list = []

    async def fake(cfg_, http, msgs, **kw):
        seen.append("\n".join(m["content"] for m in msgs))
        room = msgs[-1]["content"].split()[-1]
        return json.dumps({"text": "...", "actions": [{"type": "map", "room": room}]}), "x"
    monkeypatch.setattr(llm, "chat", fake)
    ask = lambda q: c.post("/api/assistant", headers=tma(1), json={"q": q}).json()  # noqa: E731

    assert "first digit" not in assistant.SYSTEM and "Independence" not in assistant.SYSTEM  # the guessing rule is gone
    r = ask("\u0413\u0434\u0435 404")                                       # "Where is 404"
    assert "404: floor 4." in seen[-1] and r["actions"] == [{"type": "map", "room": "404"}]
    r = ask("67")                                                           # not on the map
    assert "67: not on the app's map, its floor and place unknown" in seen[-1] and "67: floor" not in seen[-1]
    assert r["actions"] == []                                               # nothing made up opens
    r = ask("\u0430\u0443\u0434 251\u0430")                                 # "aud 251a", the Cyrillic a: the map's 251a
    assert "251a: floor 2." in seen[-1] and r["actions"] == []              # the fake's Cyrillic room isn't the map's id
    ask("\u043f\u0430\u0440\u0430 \u0432 10:30")                            # "class at 10:30": no room at all
    assert "Rooms the question names" not in seen[-1]
