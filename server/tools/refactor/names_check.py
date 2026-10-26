"""Undefined globals and unused imports in each module of a directory (stdlib only). argv: dir"""
import ast, builtins, symtable, sys
from pathlib import Path
bad = 0
for f in sorted(Path(sys.argv[1]).glob("*.py")):
    src = f.read_text(); top = symtable.symtable(src, str(f), "exec")
    defined = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    refs = set()
    def walk(t):
        for s in t.get_symbols():
            if s.is_referenced() and (s.is_global() or t is top) and not s.is_local() or (t is top and s.is_referenced()):
                refs.add(s.get_name())
        for c in t.get_children():
            walk(c)
    walk(top)
    undefined = sorted(r for r in refs if r not in defined and not hasattr(builtins, r) and r != "__file__")
    tree = ast.parse(src)
    imported = {}
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)) and not (isinstance(n, ast.ImportFrom) and n.module == "__future__"):
            for a in n.names:
                imported[(a.asname or a.name).split(".")[0]] = n.lineno
    loads = {x.id for x in ast.walk(tree) if isinstance(x, ast.Name)} | {x.value.id for x in ast.walk(tree) if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)}
    unused = sorted(k for k in imported if k not in loads) if f.name != "__init__.py" else []
    if undefined or unused:
        bad += 1
        print(f.name, "undefined:", undefined, "unused imports:", unused)
print("modules with problems:", bad)
