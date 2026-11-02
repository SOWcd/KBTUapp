"""A frame over my photo on the lanyard (logic.FRAMES): picked apart from the lanyard, seen on my card by others."""
from __future__ import annotations

from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_frame(env):
    c, _ = env
    me, other = login(c, 40, "fra"), login(c, 41, "oth")
    H = tma(40, "Fra")
    assert c.patch("/api/me", json={"frame": "nope"}, headers=H).status_code == 400   # only the app's own frames
    assert c.patch("/api/me", json={"frame": "flowers"}, headers=H).json()["frame"] == "flowers"
    assert c.patch("/api/me", json={"skin": None}, headers=H).json()["frame"] == "flowers"   # a lanyard keeps the frame
    assert c.get(f"/api/users/{me['id']}", headers=tma(41, "Oth")).json()["frame"] == "flowers"
    assert c.patch("/api/me", json={"frame": None}, headers=H).json()["frame"] is None
    assert c.patch("/api/me", json={"frame": "space"}, headers=tma(99, "Guest")).status_code in (401, 403)
