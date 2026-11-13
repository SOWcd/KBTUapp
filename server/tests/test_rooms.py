"""The map's "free now": tools/rooms.py reads a made-up timetable scrape into busy hours by room (the main building's
numbered rooms the map has, nothing else), and /api/map/rooms serves the file, or 404 without it (the feature is off)."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

from test_core import env, tma  # noqa: F401  (env: the fixture)

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import rooms  # noqa: E402

L, P = "\u041b", "\u041f"  # lecture, practice
ONLINE = "\u041e\u043d\u043b\u0430\u0439\u043d"
BLDG2 = "(\u043a\u043e\u0440\u043f\u0443\u0441 \u21162)"


def ev(day, start, hours, raw):
    return {"day": day, "start": start, "hours": hours, "room": "", "teacher": "Ivanov I.", "raw": raw}


PROGRESS = {"done": {
    "MATH101": {"name": "Calculus", "events": [
        ev(1, 9, 2, f"Calculus Ivanov I. {L} 305 (40/60)"),
        ev(1, 14, 1, f"Calculus Ivanov I. {P} 251\u0430 (12/30)"),     # a Cyrillic letter: the map's 251a
        ev(3, 10, 1, f"Calculus Ivanov I. {P} 251 \u0410 (12/30)"),    # "251 A": the same room
        ev(2, 9, 1, f"Calculus Ivanov I. {L} {ONLINE} (40/60)"),       # online: no room
        ev(2, 9, 1, f"Calculus Ivanov I. {P} 312 {BLDG2} (10/20)"),     # the second building's 312
        ev(2, 9, 1, f"Calculus Ivanov I. {P} 999 (10/20)"),            # not on the map: listed, skipped
        ev(None, None, 1, f"Calculus Ivanov I. {L} 305 (40/60)"),      # no time
    ]},
}}


def test_tool_parses_and_keeps_only_hours():
    assert rooms.room_of(f"X Y {L} 251\u0430 (1/2)") == "251a" and rooms.room_of(f"X Y {P} 312 {BLDG2}") is None
    got, missing = rooms.busy(PROGRESS, {"305", "251a", "312"})
    assert got == {"305": {"1": [9, 10]}, "251a": {"1": [14], "3": [10]}}
    assert missing == ["999"]
    assert "Ivanov" not in json.dumps(got) and "Calculus" not in json.dumps(got)


def test_endpoint_with_and_without_the_file(env, tmp_path):  # noqa: F811
    c, cfg = env
    path = tmp_path / "rooms.json"
    c.app.state.cfg = dataclasses.replace(cfg, rooms_file=str(path))
    assert c.get("/api/map/rooms", headers=tma(1)).status_code == 404  # no file: off
    path.write_text(json.dumps({"updated": "2026-11-13T10:00:00", "rooms": {"305": {"1": [9]}}}))
    assert c.get("/api/map/rooms", headers=tma(1)).json()["rooms"] == {"305": {"1": [9]}}
    assert c.get("/api/map/rooms").status_code == 403  # signed-in users only
    path.write_text(json.dumps({"updated": "2026-11-14T10:00:00", "rooms": {}}))
    os.utime(path, (1, 1))  # a new file: read again
    assert c.get("/api/map/rooms", headers=tma(1)).json()["rooms"] == {}
