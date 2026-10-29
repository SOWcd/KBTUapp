"""An organizers' sheet of expected people (.xlsx) -> JSON for `admin checkin new` (kbtu/checkin.py). Standard library
only. The file never enters the repo. Columns are found by their header words (the volunteers' sheet, Oct 29: No,
student ID, full name, name in English, KBTU mail, phone, Telegram nick, school, year, then up to three classes
excused with time and teacher); rows without a mail are skipped. Phones as +7 (700) 000 00 00.
    python3 -I tools/checkin_convert.py <sheet.xlsx> <out.json>"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# header word (lower case, first match) -> field; the Cyrillic is escaped (the repo's text is English)
FIELDS = [("id \u0441\u0442\u0443\u0434\u0435\u043d\u0442\u0430", "studentId"), ("\u043d\u0430 \u0430\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u043e\u043c", "nameEn"),
          ("\u0444\u0438\u043e", "name"), ("\u043f\u043e\u0447\u0442\u0430", "email"), ("\u0442\u0435\u043b", "phone"),
          ("\u0442\u0435\u043b\u0435\u0433\u0440\u0430\u043c", "tg"), ("\u0448\u043a\u043e\u043b\u0430", "school"), ("\u0433\u043e\u0434", "course")]

LATIN = str.maketrans('\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425', 'ABEKMHOPCTX')


def cells(path: str) -> list[dict[str, str]]:
    z = zipfile.ZipFile(path)
    shared = [''.join(t.text or '' for t in si.iter(M + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si')] \
        if 'xl/sharedStrings.xml' in z.namelist() else []
    out = []
    for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).iter(M + 'row'):
        r = {}
        for c in row.findall(M + 'c'):
            v = c.find(M + 'v')
            text = (shared[int(v.text)] if c.get('t') == 's' else v.text) if v is not None else ''.join(t.text or '' for t in c.iter(M + 't'))
            if text and text.strip():
                r[re.sub(r'\d', '', c.get('r'))] = text.strip()
        out.append(r)
    return out


def phone(raw: str) -> str | None:
    d = re.sub(r'[^0-9]', '', raw)
    d = '7' + d[1:] if len(d) == 11 and d[0] == '8' else '7' + d if len(d) == 10 else d
    return f'+7 ({d[1:4]}) {d[4:7]} {d[7:9]} {d[9:]}' if re.fullmatch(r'7\d{10}', d) else None


def convert(path: str) -> list[dict]:
    rows = cells(path)
    head_i = next(i for i, r in enumerate(rows) if any('\u043f\u043e\u0447\u0442\u0430' in v.lower() for v in r.values()))
    cols, taken = {}, set()
    for col, title in rows[head_i].items():
        t = ' '.join(title.lower().split())
        for word, field in FIELDS:
            if word in t and field not in taken:
                cols[col] = field; taken.add(field)
                break
    classes = sorted(c for c in rows[head_i + 1] if c not in cols) if head_i + 1 < len(rows) else []  # sub-headers: class, time, teacher x3
    people = []
    for r in rows[head_i + 2:]:
        p = {f: r[c] for c, f in cols.items() if c in r}
        if '@' not in p.get('email', ''):
            continue
        p['email'] = p['email'].strip().lower()
        p['phone'] = phone(p.get('phone', '')) or p.get('phone')
        p['tg'] = (p.get('tg') or '').lstrip('@') or None
        # a Cyrillic look-alike typed for the Latin letter ("24\u0412..." for 24B..., 6 rows on Oct 29)
        p['studentId'] = (p.get('studentId') or '').strip().upper().translate(LATIN) or None
        p['course'] = int(p['course']) if str(p.get('course', '')).isdigit() else None
        cls = [r.get(c) for c in classes]
        p['extra'] = {'nameEn': p.pop('nameEn', None),
                      'classes': [{'subject': s, 'time': tm, 'teacher': tc} for s, tm, tc in zip(cls[0::3], cls[1::3], cls[2::3]) if s]}
        people.append(p)
    return people


if __name__ == '__main__':
    got = convert(sys.argv[1])
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(got, f, ensure_ascii=False, indent=1)
    print(len(got), 'people;', sum(1 for p in got if p['studentId']), 'with an ID;', sum(1 for p in got if p['phone'] and p['phone'].startswith('+7 (')), 'phones')
