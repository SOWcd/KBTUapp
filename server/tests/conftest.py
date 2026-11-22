import os

import pytest

from kbtu import db


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


@pytest.fixture
def before_notification_migration():
    def rewind(con):
        # later migrations first (rewinding to 212 replays 213 and 214)
        con.executescript("""ALTER TABLE registrations DROP COLUMN rating_dismissed;
            ALTER TABLE event_ratings DROP COLUMN public_after;
            DROP TABLE notification_days;
            ALTER TABLE users DROP COLUMN notification_undo;
            ALTER TABLE users DROP COLUMN n_door;
            ALTER TABLE users DROP COLUMN n_digests;
            ALTER TABLE users DROP COLUMN n_broadcasts;""")
    return rewind


@pytest.fixture
def before_door_migration(before_notification_migration):
    """Restore the old door schema for tests that replay historical migrations on a populated database."""
    def rewind(con):
        before_notification_migration(con)
        con.executescript("""DROP TABLE door_misses;
            DROP TABLE retired_tickets;
            DROP TRIGGER signup_phone_changed;
            DROP TRIGGER signup_phone_unlinked;
            ALTER TABLE registrations DROP COLUMN phone_shared;
            DROP TRIGGER qr_hand_expected_gone;
            DROP TRIGGER qr_expected_key;
            DROP INDEX qr_expected_door_key;
            ALTER TABLE qr_expected DROP COLUMN door_key;
            CREATE TRIGGER qr_hand_expected_gone AFTER DELETE ON qr_expected BEGIN
                DELETE FROM qr_hand_marks WHERE session_id = old.session_id AND who = 'x' || old.email;
            END;""")
    return rewind


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
