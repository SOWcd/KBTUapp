"""Where a route lives, without reading app.py: one line per route, `METHOD path  app.py:line  handler → the rule
modules it calls`. Reads app.py's source (ast), imports nothing, so it runs without the venv:
python3 tools/routes.py [text]   # only the routes whose path or handler contains `text`, e.g. `tools/routes.py tickets`"""
import ast
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "kbtu" / "app.py"
METHODS = {"get", "post", "put", "patch", "delete"}


def _modules(tree: ast.Module) -> set[str]:
    """The kbtu modules app.py imports (`from . import x`, `from .logic import y`): the calls worth listing."""
    out = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            out |= {a.asname or a.name for a in node.names if a.name[0].islower()}
    return out


def _calls(fn: ast.AST, mods: set[str]) -> list[str]:
    """`logic.seats.take`, `qr.scan`, ...: the dotted calls into kbtu modules, in order, each once."""
    seen: dict[str, None] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            parts, f = [], node.func
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name) and f.id in mods and parts:
                seen[".".join([f.id, *reversed(parts)])] = None
    return list(seen)


def routes() -> list[tuple[str, str, int, str, list[str]]]:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    mods = _modules(tree)
    consts = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
              for t in n.targets if isinstance(t, ast.Name)}   # MATCH_SCORE_ROUTE = "/api/..."
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in fn.decorator_list:
            if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in METHODS and d.args):
                continue
            a = d.args[0]
            path = a.value if isinstance(a, ast.Constant) else consts.get(a.id) if isinstance(a, ast.Name) else None
            if isinstance(path, str):
                out.append((d.func.attr.upper(), path, fn.lineno, fn.name, _calls(fn, mods)))
    return sorted(out, key=lambda r: r[2])


if __name__ == "__main__":
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    for method, path, line, name, calls in routes():
        if want in path or want in name:
            print(f"{method:6} {path}  app.py:{line}  {name}" + (f" → {', '.join(calls)}" if calls else ""))
