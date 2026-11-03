"""The voluntary "Support the app" page (DONATE_PHONE): no env, no number anywhere; set, /api/me carries it, the
config's repr never prints it, a typo stops the start. The number here is a fake."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kbtu import app as server, config
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

FAKE = "+77000000000"


def test_donate_number_only_with_env(env):
    c0, cfg0 = env
    login(c0, 1, "ann")
    assert "donate" not in c0.get("/api/me", headers=tma(1)).json()
    cfg = dataclasses.replace(cfg0, donate_phone=FAKE)
    assert TestClient(server.create(cfg)).get("/api/me", headers=tma(1)).json()["donate"] == FAKE
    assert FAKE not in repr(cfg)


def test_donate_phone_checked():
    assert config._kz_phone("") == ""
    assert config._kz_phone("+7 700 000 00 00") == config._kz_phone("8 (700) 000-00-00") == FAKE
    for bad in ("+7 700 000 00", "+1 202 555 0100", "7000000000000"):
        assert config._kz_phone(bad) == ""                                  # the page off, the app up
