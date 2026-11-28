import dataclasses
import inspect
import os
import re

import pytest
from fastapi import routing
from fastapi.dependencies import models

from kbtu import app as server, db

_ROUTES: dict = {}  # (path, endpoint code) -> (its defaults, annotations and route arguments, the route's FastAPI analysis)
_NAMES: dict = {}  # an endpoint's annotations -> the global names they read


class _Handler:
    """A route's request handler, built when the route is first asked (a test asks a few of the ~430)."""

    def __init__(self, route) -> None:
        self.route = route

    async def __call__(self, scope, receive, send) -> None:
        if self.route.app is self:
            self.route.app = routing.request_response(self.route.get_route_handler())
        await self.route.app(scope, receive, send)


@pytest.fixture(scope="session", autouse=True)
def _route_cache():
    """Most tests build their own app (server.create), and FastAPI analyses each of its ~430 endpoints again: their
    signatures, string annotations and pydantic adapters (0.1-1 s an app, most of a test's setup). An endpoint is a
    fresh closure per app, but its code, defaults, path and route arguments are the same, so the analysis is too: the
    first app's is kept, and a later route takes a copy with its own endpoint and overrides provider, and builds its
    handler from them the way FastAPI's constructor does, on its first request. A default that differs (a closure's
    own Depends: json_body) misses the cache and is analysed afresh.
    ponytail: leans on FastAPI keeping a route's state in its instance attributes and Dependant being a dataclass
    (fastapi==0.162.2), as _forget_apps leans on its private endpoint caches; the assert below catches a new
    attribute tied to the endpoint, and dropping both fixtures is the way back if an upgrade changes that."""
    real = server._Route.__init__

    def init(self, path, endpoint, *, dependency_overrides_provider=None, **kw):
        fn = inspect.unwrap(endpoint)
        notes = tuple(fn.__annotations__.items())  # strings (kbtu.app has `from __future__ import annotations`)
        if (names := _NAMES.get(notes)) is None:
            names = _NAMES[notes] = tuple({n for _, a in notes if isinstance(a, str) for n in re.findall(r"[A-Za-z_]\w*", a)})
        # what those names stand for now: a test that patches one (server.Me) before create() misses the cache
        key = (repr(fn.__defaults__), repr(fn.__kwdefaults__), repr(sorted(kw.items())), notes,
               tuple(id(fn.__globals__.get(n)) for n in names))
        at = (path, endpoint.__code__, fn.__code__)
        if (kept := _ROUTES.get(at)) is None or kept[0] != key:
            real(self, path, endpoint, dependency_overrides_provider=dependency_overrides_provider, **kw)
            # one per route, a missed one replacing it; nothing of this app kept (its endpoint, pool, connections)
            seen = {k: v for k, v in vars(self).items() if k not in ("endpoint", "app", "dependency_overrides_provider")}
            seen["dependant"] = dataclasses.replace(self.dependant, call=None)
            assert not any(v is endpoint for v in seen.values()), "a route attribute holds the endpoint: copy it per app"
            _ROUTES[at] = key, seen
            return
        seen = kept[1]
        vars(self).update(seen)
        self.endpoint, self.dependency_overrides_provider = endpoint, dependency_overrides_provider
        self.dependant = dataclasses.replace(seen["dependant"], call=endpoint, dependencies=list(seen["dependant"].dependencies))
        self.app = _Handler(self)

    server._Route.__init__ = init
    yield
    server._Route.__init__ = real


@pytest.fixture(autouse=True)
def _forget_apps():
    """FastAPI's caches of what kind each endpoint is (fastapi.dependencies.models, up to 4096 each) hold the endpoint,
    and through its closure the whole app and its open database connections: emptied after each test, a worker no
    longer carries every earlier test's app (a bigger heap to collect, slower to exit)."""
    yield
    for cached in (models._is_gen_callable_cached, models._is_async_gen_callable_cached, models._is_coroutine_callable_cached):
        cached.cache_clear()


@pytest.fixture
def dmp_on(monkeypatch):
    """Attendance required is hidden (profiles.DMP_ON, owner Nov 10); its tests run it as if on."""
    from kbtu.logic import profiles
    monkeypatch.setattr(profiles, "DMP_ON", True)
    monkeypatch.setattr(profiles, "ACHIEVEMENTS", [*profiles.ACHIEVEMENTS, profiles.DMP])


@pytest.fixture
def media_dns(monkeypatch):
    """Media transport tests resolve their synthetic hosts locally and send only to MockTransport."""
    from kbtu import download
    async def addresses(host):
        return ["93.184.216.34"]
    monkeypatch.setattr(download, "_addresses", addresses)


@pytest.fixture(autouse=True)
def no_receipt_audit(monkeypatch):
    """A clean receipt's random spot-check (seats._audit, 1 in 5) is off; its own tests switch it on."""
    from kbtu.logic import seats
    monkeypatch.setattr(seats, "_audit", lambda: False)


@pytest.fixture(autouse=True)
def fresh_process_memory(monkeypatch):
    """A worker's in-memory state starts empty in every test, so a test passes the same in any order and on any
    worker: chatlist._unheld (a chat with no club, kept 10 min: an earlier test's chat -100 made
    test_live_list_union_order_and_cap's club chat count as unheld now and then), llm._rest (a provider resting after
    another test's 502s) and the usage counters' per-day budget, uniques, per-key caps and the page's counters (logic.stats)."""
    from kbtu import llm
    from kbtu.logic import chatlist, stats
    monkeypatch.setattr(chatlist, "_unheld", {})
    monkeypatch.setattr(llm, "_rest", {})
    monkeypatch.setattr(stats, "_spent", {})
    monkeypatch.setattr(stats, "_spent_day", 0)
    monkeypatch.setattr(stats, "_uniq", set())
    monkeypatch.setattr(stats, "_used", {})
    monkeypatch.setattr(stats, "_page", {})
    monkeypatch.setattr(stats, "_page_day", 0)
    monkeypatch.setattr(stats, "_ips", {})
    monkeypatch.setattr(stats, "_ips_minute", 0)


@pytest.fixture(scope="session")
def _schema_db(tmp_path_factory):
    """The schema and every migration, built once per test process; each env starts from a copy (db.init then finds
    nothing left to do but still runs its `after` catch-up)."""
    path = tmp_path_factory.mktemp("schema") / "t.db"
    db.init(str(path))
    return path


def pytest_collection_modifyitems(config, items):
    """SHARD=i/n keeps every n-th test from the i-th: CI runs the suite as n jobs side by side."""
    if shard := os.environ.get("SHARD"):
        i, n = map(int, shard.split("/"))
        keep = items[i::n]
        config.hook.pytest_deselected(items=[x for k, x in enumerate(items) if k % n != i])
        items[:] = keep
