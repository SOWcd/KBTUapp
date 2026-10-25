"""kbtu/logic.py (one file) into the package kbtu/logic/, by domain. argv: server dir. Prints checks, writes the files.

To change the layout on main (after other branches merged into logic/):
    .venv/bin/python tools/refactor/rejoin.py .        # the package back into one logic.py, the split's rewrites undone
    .venv/bin/python tools/refactor/split.py .         # cut again by ANCHORS below
    .venv/bin/python tools/refactor/names_check.py kbtu/logic && .venv/bin/python -m pytest -q
A module is the run of top-level names from one anchor to the next (in the file's order); OVERRIDE moves single names.
The clock and the limits tests patch (PATCHED) are read through their module when a function runs, so a test patches
that module (logic.core.now, logic.profiles.FIRST_N, logic.oversight.set_role): rename those in tests/ if they move."""
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

server = Path(sys.argv[1])
src_path = server / "kbtu" / "logic.py"
src = src_path.read_text()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)

# (first line, module) in the original file's numbering; a node goes to the last range starting at or before it
# a node goes to the module of the last anchor (a name) at or before it, in the file's order
ANCHORS = [('HOLD', 'core'), ('GOV_SLUG', 'core'), ('_volunteers_view', 'seats'), ('AI_TRIES', 'queues'), ('video_shape', 'queues'),
           ('end_of', 'seats'), ('SETTINGS', 'account'), ('_visible', 'seats'), ('org_shape', 'clubs'), ('schedule', 'account'),
           ('post_shape', 'newsfeed'), ('CLUB_REAPPLY', 'clubs'), ('TG_LINK', 'chatlist'), ('QUIET_FOR', 'oversight'),
           ('COMMENTS_A_MINUTE', 'moderation'), ('attended', 'profiles'), ('FRIEND_ASKS_A_DAY', 'profiles'), ('_staff_event', 'organizing'),
           ('MEMO_ASKS', 'daily'), ('saved_day', 'daily'), ('_meeting_ok', 'organizing'), ('_admin', 'oversight'), ('create_org', 'clubs'),
           ('set_role', 'oversight'), ('team', 'teams'), ('PUBLIC_AT', 'forum')]  # forum: sower4d/forum-people
OVERRIDE = {"_once": "core", "PERSON_COLS": "core", "PERSON": "core"}
DOCS = {
    "core": "The ground every rule stands on: the caller, errors, the clock, queries, rights; and the shapes the app gets (web/src/lib/api/types.ts).",
    "seats": "Events for students: the lists, registration and seats, receipts, volunteers, event chats, the channel, calendars.",
    "queues": "The bot's background work queues: the AI translator (ai.py) and videos (video.py).",
    "account": "Me: the profile, settings, the Microsoft sign-in, my photo, my schedule, deleting my data.",
    "clubs": "Clubs and schools: the list, joining, the club's own profile, starting a club, creating and naming orgs.",
    "newsfeed": "News: posts, the feed, reactions.",
    "chatlist": "Telegram chats: KBTU's directory and an org's own chats.",
    "oversight": "The app's own team and DMP: admins, moderators, bans, the audit log, the admin's clubs, DMP's registry.",
    "moderation": "Comments, reports, take-downs and their undo.",
    "profiles": "People's pages, awards and friends: streaks, achievements, grants, the first 500, friend requests and links.",
    "organizing": "Running an event: creating, editing, publishing, the door, attendees, ratings, the album.",
    "daily": "The daily rounds, the weekly memo to DMP, and the admin's numbers.",
    "teams": "A club's team: ranks, roles, departments, invite links.",
    "forum": "F1 find people: skills, requests, contact by double opt-in, blocks, pings (PLAN F1).",
}
# read through their module at call time, so a test's monkeypatch (or app.py's ICS_KEY) reaches every caller
PATCHED = {"now", "FIRST_N", "PROFILES_A_DAY", "REPORTS_A_DAY", "set_role", "ICS_KEY"}

body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom)) and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n is tree.body[0])]
imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
head_end = max(n.end_lineno for n in imports)


def first_line(n):
    return min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])


_where = {}


def mod_of(n):
    names = names_of(n)
    for x in names:
        if x in OVERRIDE:
            return OVERRIDE[x]
    return _where[id(n)]


def names_of(n):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [n.name]
    ts = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, (ast.AnnAssign, ast.AugAssign)) else []
    return [x.id for t in ts for x in ([t] if isinstance(t, ast.Name) else t.elts if isinstance(t, ast.Tuple) else []) if isinstance(x, ast.Name)]


_cur, _anch = None, dict(ANCHORS)
for n in body:
    for x in names_of(n):
        if x in _anch:
            _cur = _anch[x]
    assert _cur, f"no anchor before {names_of(n)}"
    _where[id(n)] = _cur

# each node's text: from the end of the one before (its comments come along) to its end
chunks, prev_end = [], head_end
for n in body:
    chunks.append((n, prev_end, n.end_lineno))
    prev_end = n.end_lineno
tail = "".join(lines[prev_end:])
assert not tail.strip(), "text after the last node"

defined = {}
for n, _, _ in chunks:
    for x in names_of(n):
        defined[x] = mod_of(n)
mods = [m for m in dict.fromkeys(m for _, m in ANCHORS) if m in set(_where.values()) | set(OVERRIDE.values())]  # an anchor not in this file: no module
clash = [m for m in mods if m in defined]
assert not clash, f"module names that are also logic names: {clash}"

# per module: text with PATCHED references rewritten, names used, names defined
out_nodes = defaultdict(list)
for n, a, b in chunks:
    out_nodes[mod_of(n)].append((n, a, b))
import_names = {}  # name -> import line
for n in imports:
    if isinstance(n, ast.Import):
        for al in n.names:
            import_names[al.asname or al.name] = f"import {al.name}"
    elif n.module == "__future__":
        continue
    else:
        mod = ("." * n.level) + (n.module or "")
        mod = "." + mod if n.level else mod  # one package deeper now
        for al in n.names:
            import_names[al.asname or al.name] = (mod, al.name)

report = []
files = {}
for m in mods:
    nodes = out_nodes[m]
    used, rewrites, loaded_at_import = set(), [], set()
    for n, a, b in nodes:
        local_assigned = set()
        for x in ast.walk(n):
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                args = x.args
                local_assigned |= {p.arg for p in args.args + args.kwonlyargs + args.posonlyargs}
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store) and x is not n:
                local_assigned.add(x.id)
        for x in ast.walk(n):
            if isinstance(x, ast.ImportFrom) and x.level:  # an import inside a function: kbtu's modules are one level up now
                rewrites.append((x.lineno, x.col_offset, x.col_offset + len("from "), "from ."))
            if isinstance(x, ast.Name):
                used.add(x.id)
                if x.id in PATCHED and defined.get(x.id) not in (None, m) and isinstance(x.ctx, ast.Load):
                    assert x.id not in local_assigned, f"{x.id} shadowed in {names_of(n)}"
                    rewrites.append((x.lineno, x.col_offset, x.end_col_offset, f"{defined[x.id]}.{x.id}"))
        # what runs when the module is imported: statements, decorators, defaults (annotations are strings)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            at_import = [*n.decorator_list, *n.args.defaults, *[d for d in n.args.kw_defaults if d]]
        elif isinstance(n, ast.ClassDef):
            at_import = [*n.decorator_list, *n.bases, *[s for s in n.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]]
        else:
            at_import = [n]
        for e in at_import:
            for x in ast.walk(e):
                if isinstance(x, ast.Name):
                    loaded_at_import.add(x.id)
    text = lines[:]
    by_line = defaultdict(list)
    for ln, c0, c1, new in rewrites:
        by_line[ln].append((c0, c1, new))
    for ln, rs in by_line.items():
        s = text[ln - 1].encode()  # the AST's columns count UTF-8 bytes
        for c0, c1, new in sorted(rs, reverse=True):
            s = s[:c0] + new.encode() + s[c1:]
        text[ln - 1] = s.decode()
    code = "".join("".join(text[a:b]) for _, a, b in nodes).lstrip("\n")
    own = {x for n, _, _ in nodes for x in names_of(n)}
    need = defaultdict(set)
    for x in used - own:
        if x in defined and not (x in PATCHED and defined[x] != m):
            need[defined[x]].add(x)
    patched_mods = sorted({new.split(".")[0] for *_, new in rewrites if not new.startswith("from")})
    early = sorted(x for x in loaded_at_import - own if x in defined and defined[x] != "core")
    if early:
        report.append(f"{m}: needs at import time from other modules: {early}")
    std, pkg = [], []
    for x in sorted(used):
        imp = import_names.get(x)
        if imp is None or x in own:
            continue
        if isinstance(imp, str):
            std.append(imp)
        elif not imp[0].startswith("."):  # from the standard library: with the other standard imports
            std.append(f"from {imp[0]} import {imp[1]}")
        else:
            pkg.append(imp)
    head = [f'"""{DOCS[m]}"""', "from __future__ import annotations", ""]
    head += sorted(set(std), key=lambda s: (s.startswith("from"), s.split()[1]))
    if pkg:
        if std:
            head.append("")
        groups = defaultdict(list)
        for mod, nm in pkg:
            groups[mod].append(nm)
        for mod in sorted(groups):
            head.append(f"from {mod} import {', '.join(sorted(groups[mod]))}")
    local = []
    if patched_mods:
        local.append(f"from . import {', '.join(patched_mods)}")
    files[m] = (head, local, need, code)

def wrap(prefix, names, width=120):
    if len(prefix) + len(", ".join(names)) + 16 <= width:  # 16: room for a trailing noqa
        return prefix + ", ".join(names)
    out, line = [], prefix + "("
    for nm in names:
        piece = nm + ", "
        if len(line) + len(piece) > width:
            out.append(line.rstrip())
            line = "    "
        line += piece
    out.append(line.rstrip().rstrip(",") + ")")
    return "\n".join(out)

pkg_dir = server / "kbtu" / "logic"
pkg_dir.mkdir(exist_ok=True)
for m, (head, local, need, code) in files.items():
    parts = []
    late = [x[len("from . import "):].split(", ") for x in local if x and x.startswith("from . import ")]
    late = late[0] if late else []
    top = [x for x in local if x and not x.startswith("from . import ")]
    if m != "core" and need.get("core"):
        top.append(wrap("from .core import ", sorted(need["core"])))
    parts.append("\n".join(head) + ("\n\n" + "\n".join(top) if top else ""))
    parts.append(code.rstrip("\n"))
    rest = {k: v for k, v in need.items() if k != "core" or m == "core"}
    bottom = [wrap(f"from .{k} import ", sorted(v)) + "  # noqa: E402" for k, v in sorted(rest.items())]
    if late:  # the clock and the limits tests patch: read through their module when a function runs
        bottom.insert(0, f"from . import {', '.join(late)}  # noqa: E402")
    if bottom:
        parts.append("# the other domains', imported last: they import this one too, and each needs the other's names only\n"
                     "# when a function runs\n" + "\n".join(bottom))
    text = "\n\n\n".join(parts) + "\n"
    text = text.replace("Path(__file__).with_name(", "Path(__file__).parent.with_name(")  # one directory deeper now
    (pkg_dir / f"{m}.py").write_text(text)

doc = ast.get_docstring(tree)
init = [f'"""{doc}\n\nSplit by domain into the modules beside this file (owner, Oct 25); everything is re-exported here, so callers\nuse kbtu.logic as before. A test that patches the clock or a limit patches the module that holds it (logic.core.now).\n"""']
init.append("from __future__ import annotations")
for m in mods:
    names = sorted(x for x, d in defined.items() if d == m)
    init.append(wrap(f"from .{m} import ", names) + "  # noqa: F401")
# what callers took from the old module that it only imported (logic.tx, logic.media, ...)
ext = set()
for f in [*server.glob("kbtu/*.py"), *server.glob("tests/*.py"), *server.glob("tools/*.py")]:
    for x in ast.walk(ast.parse(f.read_text())):
        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "logic":
            ext.add(x.attr)
        if isinstance(x, ast.ImportFrom) and x.module and x.module.split(".")[-1] == "logic":
            ext |= {al.name for al in x.names}
borrowed = defaultdict(list)
for x in sorted(ext - set(defined) - set(mods)):
    imp = import_names.get(x)
    assert imp is not None, f"callers use logic.{x}, which it neither defined nor imported"
    if isinstance(imp, str):
        init.append(f"{imp}  # noqa: F401")
    else:
        borrowed[imp[0]].append(imp[1])
for mod, nm in sorted(borrowed.items()):
    init.append(f"from {mod} import {', '.join(nm)}  # noqa: F401  (callers took these from the old module)")
(pkg_dir / "__init__.py").write_text("\n\n".join(init[:2]) + "\n\n" + "\n".join(init[2:]) + "\n")
src_path.unlink()
print("\n".join(report) or "no import-time cross-module needs")
for m in mods:
    print(f"{m:12s} {len((pkg_dir / (m + '.py')).read_text().splitlines()):5d} lines")
