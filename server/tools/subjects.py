"""The subjects' cards ("find people to study it with"): the university's subjects from a scrape of the portal's course list.

    python3 -I tools/subjects.py SCRAPE.json OUT.json

SCRAPE.json: {"done": {"CODE|year|term": {"cells": [code, ru, kk, en, school, credits, formula, year, term], "items": [...]}}}
(items: the timetable's lines, never read here). OUT.json (outside the repo; the server's SUBJECTS_FILE):
{"updated": iso, "subjects": [{"id", "names": {ru, kk, en}, "alt": [other spellings], "codes", "credits", "school"}]},
nothing else: no teachers, rooms or enrolment. One card per subject: entries sharing a code, a Russian name or an
English name once folded (case, spaces, look-alike letters, Roman numerals as digits) are one card; ALIAS joins what
folding can't. The id is a hash of the card's first folded Russian name, so it stays when a new scrape renumbers codes.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

# Cyrillic look-alikes (upper and lower, the Kazakh I too) as the Latin letters the scrape mixes them with
LOOK = str.maketrans("\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0406\u0430\u0435\u043e\u0440\u0441\u0445\u0456\u0443\u043a\u043c\u0442\u043d\u0432",
                     "ABEKMHOPCTXIaeopcxiykmthb")
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
# folded names that are one subject though folding can't tell: {another: the one}. Empty until a pair shows up
ALIAS: dict[str, str] = {}


def key(name: str) -> str:
    """A name's folded form: "Calculus II", "calculus 2" and a Cyrillic look-alike spelling are one."""
    s = unicodedata.normalize("NFKC", name).lower().replace("\u0451", "\u0435").translate(LOOK)
    s = re.sub(r"(?<![^\W\d_])(i{1,3}|iv|vi?)(?![^\W\d_])", lambda m: ROMAN[m[1]], s)  # a lone Roman numeral, as a digit
    s = re.sub(r"[\W_]+", "", s)
    return ALIAS.get(s, s)


def code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.translate(LOOK).upper())


def cards(scrape: dict) -> list[dict]:
    rows = []
    for v in scrape["done"].values():
        c, ru, kk, en, school, credits = (" ".join(str(x or "").split()) for x in v["cells"][:6])
        if ru:
            rows.append({"code": code(c), "ru": ru, "kk": kk or ru, "en": en or ru, "school": school, "credits": credits})
    up = list(range(len(rows)))  # union-find over the rows: one card per connected code / Russian / English name

    def find(i: int) -> int:
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i
    seen: dict[str, int] = {}
    for i, r in enumerate(rows):
        for k in (f"c:{r['code']}" if r["code"] else "", f"r:{key(r['ru'])}", f"e:{key(r['en'])}"):
            if k and k[2:]:
                if k in seen:
                    up[find(i)] = find(seen[k])
                else:
                    seen[k] = i
    groups: dict[int, list[dict]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(find(i), []).append(r)
    out = []
    for g in groups.values():
        main = Counter((r["ru"], r["kk"], r["en"]) for r in g).most_common(1)[0][0]  # the commonest spelling names it
        names = dict(zip(("ru", "kk", "en"), main))
        alt = sorted({n for r in g for n in (r["ru"], r["kk"], r["en"])} - set(main))
        credits = Counter(r["credits"] for r in g if r["credits"].isdigit()).most_common(1)
        school = Counter(r["school"] for r in g if r["school"]).most_common(1)
        out.append({"id": hashlib.sha1(min(key(r["ru"]) for r in g).encode()).hexdigest()[:10], "names": names, "alt": alt,
                    "codes": sorted({r["code"] for r in g if r["code"]}), "credits": int(credits[0][0]) if credits else None,
                    "school": school[0][0] if school else None})
    return sorted(out, key=lambda x: x["names"]["ru"].lower())


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    out = cards(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    Path(sys.argv[2]).write_text(json.dumps({"updated": datetime.now().isoformat(timespec="seconds"), "subjects": out},
                                            ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} subjects written to {sys.argv[2]}")


if __name__ == "__main__":
    main()
