"""A class lasts 50 minutes of the portal's hour slot (owner, Nov 19)."""
from kbtu.logic.account import class_ends


def test_an_end_on_the_hour_is_ten_minutes_earlier():
    assert class_ends("15:00") == "14:50" and class_ends("09:00") == "08:50"
    assert class_ends("15:40") == "15:40" and class_ends("00:00") == "00:00"
