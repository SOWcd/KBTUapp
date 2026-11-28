from kbtu.migrations import BASE, MIGRATIONS


def test_numbers_run_one_by_one():
    """A gap or repeat would make different histories possible for the same user_version."""
    nums = [n for n, _ in MIGRATIONS]
    assert nums == list(range(BASE + 1, BASE + 1 + len(nums))), nums
