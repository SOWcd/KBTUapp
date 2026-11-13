"""The map's "free now": the class schedule's busy hours by room, from a scrape of the university's timetable.

    python3 -I tools/rooms.py PROGRESS.json OUT.json

PROGRESS.json: {"done": {subject code: {"name", "events": [{"day": 1-7 (Mon=1), "start": hour, "hours": n, "raw": ...}]}}},
where raw is "Subject Teacher L|P Room (enrolled/capacity)". OUT.json (outside the repo; the server's ROOMS_FILE):
{"updated": iso, "rooms": {room: {day: [hours]}}}, the main building's numbered rooms the campus map has, and nothing
else: no teachers, no subjects, no counts. Prints the rooms of the data the map doesn't have (skipped, not an error).
The parsing follows the scrape author's filter: online, the second building, the IHN, sport halls and other places out,
Cyrillic look-alike letters folded. The escapes below are the Russian of those words.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

MAP_ROOMS = Path(__file__).resolve().parents[2] / "web/src/assets/map/uniq-rooms.json"  # the main map's rooms by floor

COUNT = re.compile(r"\s*\(\d+(?:/\d+)?\)\s*$")
# the kind before the room: lab, lecture (L), practice (P)
KIND = re.compile(r"^(?:.*\s)?(\u041b\u0410\u0411|\u041b\u0430\u0431|\u043b\u0430\u0431|\u041b|\u041f)\s+(\S.*)$")
ROOM = re.compile(r"\d+\s?[A-Za-z\u0400-\u04ff]?")
# online, offline, online, coursera; building 2 / Kazybek (its street); the IHN and other buildings
AWAY = ("\u041e\u041d\u041b\u0410\u0419\u041d", "\u041e\u0424\u0424\u041b\u0410\u0419\u041d", "ONLINE", "COURSERA",
        "\u041a\u041e\u0420\u041f\u0423\u0421", "\u041a\u0410\u0417\u042b\u0411\u0415\u041a",
        "\u0418\u0425\u041d", "SEZPIT", "\u0418\u0422\u041a\u0418\u042d")
# the map's form (web/src/lib/map.ts normRoom): lower case, the Cyrillic look-alikes Latin
FOLD = str.maketrans({"\u0430": "a", "\u0431": "b", "\u0432": "v", "\u0441": "c", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0445": "x"})
VACANCY = "\u0432\u0430\u043a\u0430\u043d\u0441\u0438\u044f"  # a placeholder teacher: the class isn't really there
TEMP = "\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0437\u0430\u043d\u044f\u0442\u0438\u044f"  # "temporary classes"


def room_of(raw: str) -> str | None:
    """The main building's numbered room of an event's raw line, in the map's form; None for anything else (a sport hall
    is never a bare number, so it falls out here too)."""
    m = KIND.match(COUNT.sub("", " ".join(raw.split())))
    if not m:
        return None
    loc = re.sub(r"^[.\s]+", "", m.group(2)).strip()
    if any(w in loc.upper() for w in AWAY) or not ROOM.fullmatch(loc):
        return None
    return loc.replace(" ", "").lower().translate(FOLD)


def busy(progress: dict, known: set[str]) -> tuple[dict, list[str]]:
    """{room: {day: [hours]}} for the rooms the map knows, and the sorted rooms it doesn't."""
    out: dict[str, dict[str, set[int]]] = {}
    missing: set[str] = set()
    for info in progress["done"].values():
        temp = info.get("name", "").strip().lower() == TEMP
        for ev in info["events"]:
            if temp and VACANCY in ev.get("raw", "").lower():
                continue
            if not ev.get("day") or not ev.get("start"):
                continue
            r = room_of(ev.get("raw", ""))
            if r is None:
                continue
            if r not in known:
                missing.add(r)
                continue
            out.setdefault(r, {}).setdefault(str(ev["day"]), set()).update(range(ev["start"], ev["start"] + (ev.get("hours") or 1)))
    rooms = {r: {d: sorted(h) for d, h in sorted(days.items())} for r, days in sorted(out.items())}
    return rooms, sorted(missing, key=lambda r: (len(r), r))


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    known = {r for floor in json.loads(MAP_ROOMS.read_text()) for r in floor}
    rooms, missing = busy(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), known)
    Path(sys.argv[2]).write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"), "rooms": rooms}, separators=(",", ":")))
    print(f"{len(rooms)} rooms written to {sys.argv[2]}")
    print(f"{len(missing)} not on the map (skipped): {' '.join(missing)}")


if __name__ == "__main__":
    main()
