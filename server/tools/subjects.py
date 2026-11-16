"""The subjects' cards ("find people to study it with"): the university's subjects from a scrape of its timetable.

    python3 -I tools/subjects.py PROGRESS.json OUT.json

PROGRESS.json: the same scrape as tools/rooms.py ({"done": {code: {"name", "events"}}}). OUT.json (outside the repo;
the server's SUBJECTS_FILE): {"updated": iso, "subjects": [{"id", "name", "codes"}]}, one card per name (a subject
taught under several codes is one card), nothing else: no teachers, rooms or counts. The id is a hash of the name's
folded form, so it stays when a new scrape renumbers the codes. The scrape's names come in one language (mostly Russian).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# Cyrillic look-alikes (upper and lower, the Kazakh I too) as the Latin letters the scrape mixes them with
LOOK = str.maketrans("\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0406\u0430\u0435\u043e\u0440\u0441\u0445\u0456\u0443\u043a\u043c\u0442\u043d\u0432",
                     "ABEKMHOPCTXIaeopcxiykmthb")
TEMP = "\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0437\u0430\u043d\u044f\u0442\u0438\u044f"  # "temporary classes": a placeholder


def key(name: str) -> str:
    """A name's folded form: two spellings of one subject (a Latin B for a Cyrillic one, a space less) are one."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", name).lower().replace("\u0451", "\u0435").translate(LOOK))


def code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.translate(LOOK).upper())


def cards(progress: dict) -> list[dict]:
    by: dict[str, dict] = {}
    for c, info in progress["done"].items():
        name = " ".join(str(info.get("name") or "").split())
        if not name or name.lower() == TEMP:
            continue
        k = key(name)
        card = by.setdefault(k, {"id": hashlib.sha1(k.encode()).hexdigest()[:10], "name": name, "codes": []})
        if (cc := code(c)) and cc not in card["codes"]:
            card["codes"].append(cc)
    return sorted(({**x, "codes": sorted(x["codes"])} for x in by.values()), key=lambda x: x["name"].lower())


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    out = cards(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    Path(sys.argv[2]).write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"), "subjects": out},
                                            ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} subjects written to {sys.argv[2]}")


if __name__ == "__main__":
    main()
