"""An .xlsx read with the standard library: each sheet's cells as text, as saved. Formulas are never run: a formula cell
gives the value Excel saved with it (counted, so a preview can say so). Sizes are capped: a zip bomb or a huge sheet is
refused before it is read."""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

MAX_FILE = 5 << 20       # the file itself
MAX_PART = 30 << 20      # one part of it unpacked
MAX_ALL = 60 << 20       # all its parts unpacked together
MAX_SHEETS = 20
MAX_TEXT = 20_000_000    # characters of all cells together (one shared string named by many cells)
MAX_ROWS = 3000          # rows per sheet
MAX_COLS = 200
MAX_CELL = 1000          # characters a cell keeps

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
_REF = re.compile(r"([A-Z]{1,3})(\d+)")


class Bad(ValueError):
    pass


def _xml(z: zipfile.ZipFile, name: str):
    info = z.getinfo(name)
    if info.file_size > MAX_PART:
        raise Bad(f"{name}: too big unpacked")
    data = z.read(name)
    if b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data:
        raise Bad(f"{name}: a DTD")  # no entity games
    return ET.fromstring(data)


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read(data: bytes) -> tuple[dict[str, list[list[str]]], int]:
    """{sheet name: rows of cells (text, '' empty)}, and how many formula cells gave their saved value."""
    if len(data) > MAX_FILE:
        raise Bad("file too big")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Bad("not an xlsx") from None
    names = set(z.namelist())
    if sum(i.file_size for i in z.infolist()) > MAX_ALL:
        raise Bad("too big unpacked")
    if "xl/workbook.xml" not in names:
        raise Bad("not an xlsx")
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        shared = ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in _xml(z, "xl/sharedStrings.xml").findall("m:si", _NS)]
    rels = {r.get("Id"): r.get("Target") for r in _xml(z, "xl/_rels/workbook.xml.rels").findall("p:Relationship", _NS)}
    out, formulas, seen, chars = {}, 0, set(), 0
    sheets = list(_xml(z, "xl/workbook.xml").find("m:sheets", _NS))
    if len(sheets) > MAX_SHEETS:
        raise Bad(f"more than {MAX_SHEETS} sheets")
    for sh in sheets:
        target = rels.get(sh.get(f"{{{_NS['r']}}}id"), "")
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if path not in names or path in seen:
            continue  # a part named twice is read once: no amplifying one part by many sheets
        seen.add(path)
        grid: list[list[str]] = []
        for row in _xml(z, path).iter(f"{{{_NS['m']}}}row"):
            if len(grid) >= MAX_ROWS:
                raise Bad(f"{sh.get('name')}: more than {MAX_ROWS} rows")
            cells: list[str] = []
            for c in row.findall("m:c", _NS):
                m = _REF.fullmatch(c.get("r") or "")
                i = _col(m[1]) if m else len(cells)
                if i >= MAX_COLS:
                    raise Bad(f"{sh.get('name')}: more than {MAX_COLS} columns")
                kind, v = c.get("t"), c.find("m:v", _NS)
                if c.find("m:f", _NS) is not None:
                    formulas += 1
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
                elif v is None or v.text is None:
                    text = ""
                elif kind == "s":
                    k = int(v.text)
                    text = shared[k] if 0 <= k < len(shared) else ""
                else:
                    text = v.text
                cells += [""] * (i + 1 - len(cells))
                cells[i] = text.strip()[:MAX_CELL]
                chars += len(cells[i])
                if chars > MAX_TEXT:
                    raise Bad("too much text")
            r = int(row.get("r") or len(grid) + 1) - 1
            if r >= MAX_ROWS:
                raise Bad(f"{sh.get('name')}: more than {MAX_ROWS} rows")
            grid += [[] for _ in range(r - len(grid))]  # empty rows Excel skipped
            grid.append(cells)
        out[sh.get("name") or ""] = grid
    return out, formulas


def write(sheets: dict[str, list[list[str]]]) -> bytes:
    """A minimal .xlsx of inline strings (tests build their synthetic files with it)."""
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def letters(i: int) -> str:
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="{_NS["m"]}" xmlns:r="{_NS["r"]}"><sheets>'
                   + "".join(f'<sheet name="{esc(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(sheets)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="{_NS["p"]}">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets))) + "</Relationships>")
        for i, grid in enumerate(sheets.values()):
            body = "".join(f'<row r="{r + 1}">' + "".join(f'<c r="{letters(j)}{r + 1}" t="inlineStr"><is><t>{esc(v)}</t></is></c>' for j, v in enumerate(row) if v != "")
                           + "</row>" for r, row in enumerate(grid))
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", f'<?xml version="1.0"?><worksheet xmlns="{_NS["m"]}"><sheetData>{body}</sheetData></worksheet>')
    return buf.getvalue()
