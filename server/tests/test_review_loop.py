"""An async route's database write runs off the event loop: behind another writer's lock it waits in a thread, and
the worker's other requests (/healthz) go on meanwhile."""
from __future__ import annotations

import asyncio
import io
import threading
import time

import httpx
from PIL import Image

from kbtu import db
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_upload_waits_off_the_loop(env):
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    raw = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 40, 40)).save(raw, "PNG")
    head = tma(20)
    c.get("/api/me", headers=head)  # seen_at fresh: the request's own maybe() write stays out of the way

    async def run() -> float:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app), base_url="http://t") as h:
            con.execute("BEGIN IMMEDIATE")  # another writer (a check-in burst) holds the lock 1.5 s
            threading.Timer(1.5, lambda: con.execute("COMMIT")).start()
            up = asyncio.create_task(h.post("/api/photos", headers=head, content=raw.getvalue()))
            t = time.monotonic()
            await asyncio.sleep(0.5)  # the upload is at its INSERT now
            assert (await h.get("/healthz")).status_code == 200
            took = time.monotonic() - t
            assert (await up).status_code == 200
            return took
    assert asyncio.run(run()) < 1.2  # on the loop: /healthz came only after the lock went, 1.5 s
