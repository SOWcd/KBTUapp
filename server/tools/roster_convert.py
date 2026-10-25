"""DMP's Student Union sheet (PLAN 95) into the JSON `admin roster load` takes. The file holds real students: it and the
JSON stay outside the repo, and this prints counts only, never a row.

    server/.venv/bin/python server/tools/roster_convert.py <sheet.xlsx> <out.json>

Read with the standard library (an .xlsx is a zip of XML; no new package). One org per sheet; the sheet listing the
orgs is skipped. Headers differ per sheet (position, department, full name, school, year, city, Telegram or e-mail,
phone): matched by their words, a second full-name column ignored."""
from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kbtu.roster import classify, course_of, email_of, latin, tg_of  # noqa: E402

N = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
LIST_SHEET = "organizatsii"  # the sheet of org names, in latin()


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheets(path: str):
    """(sheet name, rows as lists of cell strings) for each sheet."""
    z = zipfile.ZipFile(path)
    shared = [("".join(t.text or "" for t in si.iter(f"{{{N['m']}}}t")))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", N)] if "xl/sharedStrings.xml" in z.namelist() else []
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    for s in wb.find("m:sheets", N):
        target = rels[s.get(f"{{{N['r']}}}id")].lstrip("/")
        out = []
        for row in ET.fromstring(z.read(target if target.startswith("xl/") else "xl/" + target)).iter(f"{{{N['m']}}}row"):
            vals = {}
            for c in row.findall("m:c", N):
                v, inline = c.find("m:v", N), c.find("m:is", N)
                vals[_col(c.get("r"))] = (shared[int(v.text)] if c.get("t") == "s" and v is not None
                                          else "".join(e.text or "" for e in inline.iter(f"{{{N['m']}}}t")) if inline is not None
                                          else v.text if v is not None else None)
            out.append([vals.get(i) for i in range(max(vals) + 1)] if vals else [])
        yield s.get("name"), out


# a header's words (latin(), lowercase) -> the field; the first matching column wins
FIELDS = (("position", ("dolzhn", "member/departm")), ("dept", ("kategori", "departament", "department")), ("full_name", ("fio",)),
          ("school", ("shkol",)), ("year", ("god ", "kurs")), ("city", ("gorod",)), ("tg", ("telegram",)), ("email", ("pocht", "mail")),
          ("phone", ("telefon", "sotovi", "nomer")))


def columns(header: list) -> dict[str, int]:
    out = {}
    for i, h in enumerate(header):
        t = latin(str(h or "").strip()) + " "
        for field, keys in FIELDS:
            if field not in out and any(k in t for k in keys):
                out[field] = i
                break
    return out


def convert(path: str) -> tuple[list[dict], dict[str, int]]:
    items, per = [], {}
    for name, rows in sheets(path):
        if latin(name).strip() == LIST_SHEET or not rows:
            continue
        col = columns(rows[0])
        sheet = name.strip()
        for r in rows[1:]:
            get = lambda f: (str(r[col[f]]).strip() if f in col and col[f] < len(r) and r[col[f]] not in (None, "") else None)  # noqa: E731
            if not get("full_name") and not get("tg") and not get("email"):
                continue  # an empty or a note row
            pos, dept = get("position"), get("dept")
            if "dept" not in col and pos and latin(str(rows[0][col["position"]])).startswith("member/"):  # one column for both
                pos, dept = (pos, None) if latin(pos).strip() in ("member", "uchastnik") else (None, pos)
            role, title, dept = classify(pos, dept)
            items.append({"sheet": sheet, "position": pos, "title": title, "role": role, "dept": dept, "full_name": get("full_name"),
                          "school": get("school"), "year": get("year"), "course": course_of(get("year")), "city": get("city"),
                          "phone": get("phone"), "tg": tg_of(get("tg")), "email": email_of(get("email"))})
            per[sheet] = per.get(sheet, 0) + 1
    return items, per


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    items, per = convert(sys.argv[1])
    Path(sys.argv[2]).write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    roles = {}
    for x in items:
        roles[x["role"]] = roles.get(x["role"], 0) + 1
    print(f"{len(items)} rows from {len(per)} sheets; with Telegram {sum(1 for x in items if x['tg'])}, e-mail {sum(1 for x in items if x['email'])}, "
          f"phone {sum(1 for x in items if x['phone'])}, neither {sum(1 for x in items if not x['tg'] and not x['email'])}; roles {roles}")
    for s, n in per.items():
        print(f"  {s}: {n}")
