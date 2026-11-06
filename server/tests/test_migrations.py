"""Migrations apply by number (db.py: those above PRAGMA user_version), so a gap or a repeat would make a later one be
skipped on a live database: two branches that took the same number, merged in the wrong order (Nov 6)."""
from kbtu.db import MIGRATIONS


def test_numbers_run_one_by_one():
    nums = [n for n, _ in MIGRATIONS]
    assert nums == list(range(nums[0], nums[0] + len(nums))), nums
