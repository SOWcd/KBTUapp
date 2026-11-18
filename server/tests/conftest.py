import pytest


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
