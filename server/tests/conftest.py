import pytest

from kbtu import db


@pytest.fixture
def dmp_on(monkeypatch):
    """Attendance required is hidden (profiles.DMP_ON, owner Nov 10); its tests run it as if on."""
    from kbtu.logic import profiles
    monkeypatch.setattr(profiles, "DMP_ON", True)
    monkeypatch.setattr(profiles, "ACHIEVEMENTS", [*profiles.ACHIEVEMENTS, profiles.DMP])


@pytest.fixture(autouse=True)
def no_receipt_audit(monkeypatch):
    """A clean receipt's random spot-check (seats._audit, 1 in 5) is off; its own tests switch it on."""
    from kbtu.logic import seats
    monkeypatch.setattr(seats, "_audit", lambda: False)


@pytest.fixture(scope="session")
def _schema_db(tmp_path_factory):
    """The schema and every migration, built once per test process; each env starts from a copy (db.init then finds
    nothing left to do but still runs its `after` catch-up)."""
    path = tmp_path_factory.mktemp("schema") / "t.db"
    db.init(str(path))
    return path
