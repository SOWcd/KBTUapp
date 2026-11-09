"""Give clubs without a category one, through the app's LLM chain (name and description, both public). One-off, by hand,
after migration 143 is live; a second run only touches what is still empty. Uses the server's own env (DB_PATH, keys).

    cd server && .venv/bin/python tools/fill_categories.py
"""
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kbtu import ai, config, db  # noqa: E402


async def main() -> None:
    cfg = config.load()
    con = db.connect(cfg.db_path)
    async with httpx.AsyncClient() as http:
        print("filled %d, left empty %d" % await ai.fill_categories(con, cfg, http))


asyncio.run(main())
