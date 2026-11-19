"""SQLite: one file, WAL, foreign keys on (SPEC §5). Each request takes a connection of its own from a Pool (threads
and worker processes stay apart); a write that checks and then inserts (the last seat) runs inside `tx`, which takes
the write lock up front (BEGIN IMMEDIATE), so two requests can't both see a free seat."""
from __future__ import annotations

import contextlib
import fcntl
import queue
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from .migrations import MIGRATIONS  # in migrations.py since issue #21 (db.MIGRATIONS keeps working)

SCHEMA = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")


BUSY_MS = 15000  # a write's wait for the lock (maybe() waits less)


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(f"PRAGMA busy_timeout = {BUSY_MS}")  # a write waits its turn: 600 sign-ups at once took 11 s on a laptop core
    con.execute("PRAGMA secure_delete = ON")  # deleted rows' text doesn't linger in free pages (H2)
    con.execute("PRAGMA synchronous = NORMAL")  # with WAL: no corruption on a crash, fsync only at checkpoints
    # reads straight from the OS page cache, shared by every worker and pooled connection, instead of each copying
    # pages into its own small cache (writes still go through the WAL)
    con.execute("PRAGMA mmap_size = 268435456")
    return con


class Pool:
    """Open connections kept for the next request. A new connection reads the whole schema before its first query
    (~4 ms on a laptop core, more than most requests take; load test); a kept one starts at once. A request
    has its connection to itself until it gives it back."""

    def __init__(self, path: str) -> None:
        self.path, self.idle = path, queue.SimpleQueue()

    @contextlib.contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        try:
            con = self.idle.get_nowait()
        except queue.Empty:
            con = connect(self.path)
        try:
            yield con
        finally:
            if con.in_transaction:  # a request that died mid-write leaves nothing open for the next one
                con.execute("ROLLBACK")
            self.idle.put(con)


def init(path: str, after: Callable[[sqlite3.Connection], None] | None = None) -> None:
    """Creates the database or brings it up to date. Each step is one transaction (DDL is transactional in
    SQLite), so a failure leaves the file as it was. Worker processes start together: one migrates while the
    rest wait on the lock file, then find nothing left to do. `after` runs under the same lock (the data's own
    catch-up, e.g. achievement levels)."""
    with open(f"{path}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _init(path)
        if after:
            con = connect(path)
            try:
                after(con)
            finally:
                con.close()


def _init(path: str) -> None:
    con = connect(path)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        version = con.execute("PRAGMA user_version").fetchone()[0]
        steps = ([(1, SCHEMA)] if version == 0 else []) + [m for m in MIGRATIONS if m[0] > version]
        if version and steps:  # a live file about to change: a full copy next to it first (the way back, by hand)
            con.execute("VACUUM INTO ?", (f"{path}.v{version}-{int(time.time())}.bak",))
        for target, sql in steps:
            try:
                con.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {target};\nCOMMIT;")
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
    finally:
        con.close()


@contextlib.contextmanager
def tx(con: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A write transaction that holds the write lock from the start; inside another one it joins it (the outer one
    commits or rolls back for both)."""
    if con.in_transaction:
        yield con
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def maybe(con: sqlite3.Connection, fn: Callable, *args, ms: int = 200):
    """A best-effort write on a read (seen_at, a roster match on /api/me): fn(*args) in one transaction that waits for
    the write lock `ms` at most and is skipped (rolled back, None) while a burst holds it; the next call tries again.
    A GET never waits connect()'s 15 s behind someone else's writes."""
    con.execute(f"PRAGMA busy_timeout = {int(ms)}")
    try:
        with tx(con):
            return fn(*args)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc) and "busy" not in str(exc):
            raise
        return None
    finally:
        con.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
