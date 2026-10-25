"""kbtu/logic/ (the package) back into one kbtu/logic.py, so tools/refactor/split.py can cut it again another way: each
module's code in the package's import order, without the module's own imports, with the split's rewrites undone
(core.now() -> now(), the deeper relative imports, Path(__file__).parent). argv: server dir. The package is removed."""
import ast
import re
import shutil
import sys
from pathlib import Path

server = Path(sys.argv[1])
pkg = server / "kbtu" / "logic"
init = (pkg / "__init__.py").read_text()
order = re.findall(r"^from \.(\w+) import", init, re.M)
doc = ast.get_docstring(ast.parse(init)).split("\n\nSplit by domain")[0]
PATCHED = r"\b(?:" + "|".join(order) + r")\.(now|FIRST_N|PROFILES_A_DAY|REPORTS_A_DAY|set_role|ICS_KEY)\b"
imports, bodies = {}, []
for m in order:
    src = (pkg / f"{m}.py").read_text()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    keep = []
    first = next(n for n in tree.body if not (isinstance(n, (ast.Import, ast.ImportFrom)) or (isinstance(n, ast.Expr) and n is tree.body[0])))
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            if isinstance(n, ast.ImportFrom) and n.level == 1:
                continue  # the package's own modules: one file again
            if isinstance(n, ast.ImportFrom) and n.module == "__future__":
                continue
            text = ast.get_source_segment(src, n)
            imports[text.replace("from ..", "from .")] = True
    # the module's code: from its first statement to the line before its bottom imports
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) and n.lineno < first.lineno]
    start = max([n.end_lineno for n in top] + [tree.body[0].end_lineno])  # right after the module's own imports
    end = len(lines)
    tail = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.level == 1 and n.lineno > first.lineno]
    if tail:
        end = min(n.lineno for n in tail) - 1
        while end > start and (not lines[end - 1].strip() or lines[end - 1].startswith("# the other domains") or lines[end - 1].startswith("# when a function runs")):
            end -= 1
    body = "".join(lines[start:end]).rstrip("\n")
    body = re.sub(PATCHED, r"\1", body).replace("Path(__file__).parent.with_name(", "Path(__file__).with_name(")
    body = re.sub(r"^(\s*)from \.\. ", r"\1from . ", body, flags=re.M)
    body = re.sub(r"^(\s*)from \.\.(\w)", r"\1from .\2", body, flags=re.M)
    bodies.append(body)
std = sorted((i for i in imports if not i.startswith("from .")), key=lambda s: (s.startswith("from"), s.split()[1]))
own = sorted(i for i in imports if i.startswith("from ."))
head = f'"""{doc}"""\nfrom __future__ import annotations\n\n' + "\n".join(std) + "\n\n" + "\n".join(own) + "\n\n"
(server / "kbtu" / "logic.py").write_text(head + "\n\n\n".join(bodies) + "\n")
shutil.rmtree(pkg)
print(f"logic.py: {len((server / 'kbtu' / 'logic.py').read_text().splitlines())} lines from {len(order)} modules")
