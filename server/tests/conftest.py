import pytest


@pytest.fixture
def dmp_on(monkeypatch):
    """Attendance required is hidden (profiles.DMP_ON, owner Nov 10); its tests run it as if on."""
    from kbtu.logic import profiles
    monkeypatch.setattr(profiles, "DMP_ON", True)
    monkeypatch.setattr(profiles, "ACHIEVEMENTS", [*profiles.ACHIEVEMENTS, profiles.DMP])
