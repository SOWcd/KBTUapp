"""AGENTS.md's "server/kbtu at a glance" names every top-level module: a new one (feeds.py came without its line) fails
here until it has one. Standard library only."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_server_module_has_its_line():
    table = set(re.findall(r"^\| `([\w.]+\.py)` \|", (ROOT / "AGENTS.md").read_text(encoding="utf-8"), re.M))
    modules = {p.name for p in (ROOT / "server" / "kbtu").glob("*.py") if p.name != "__init__.py"}
    assert sorted(modules - table) == [], "add a line to AGENTS.md's `server/kbtu` at a glance"
