import pytest

from kbtu.logic.organizing import campus_place, clean_event


@pytest.mark.parametrize(("place", "canonical"), [
    ("\u0422\u04111", "\u0422\u0411 · 1 \u044d\u0442\u0430\u0436"),
    (" \u0430\u0431  2 ", "\u0410\u0411 · 2 \u044d\u0442\u0430\u0436"),
    ("\u041f\u04241", "\u041f\u0424 · 1 \u044d\u0442\u0430\u0436"),
    ("\u049a\u0430\u0437\u044b\u0431\u0435\u043a \u0431\u0438 1", "\u041a\u0411 · 1 \u044d\u0442\u0430\u0436"),
    ("\u041a\u0430\u0437\u044b\u0431\u0435\u043a\u00a0\u0431\u0438 1", "\u041a\u0411 · 1 \u044d\u0442\u0430\u0436"),
    ("\u0422\u04e9\u043b\u0435 \u0431\u0438 5-\u049b\u0430\u0431\u0430\u0442", "\u0422\u0411 · 5 \u044d\u0442\u0430\u0436"),
    ("Kazybek 1", "\u041a\u0411 · 1 \u044d\u0442\u0430\u0436"),
    ("kb · floor 4 · 412a", "\u041a\u0411 · 4 \u044d\u0442\u0430\u0436 · 412a"),
    ("TB0", "\u0422\u0411 · 0 \u044d\u0442\u0430\u0436"),
    ("AB 0", "\u0410\u0411 · 0 \u044d\u0442\u0430\u0436"),
    ("Panfilov 0", "\u041f\u0424 · 0 \u044d\u0442\u0430\u0436"),
    ("KB 0", None),
    ("\u041a\u04110", None),
    ("TB6", None),
    ("AB5", None),
    ("PF5", None),
    ("Kazybek bi 12", None),
    ("Kazybek bi 1, Almaty", None),
    ("Tole bi 59", None),
])
def test_campus_place(place, canonical):
    assert campus_place(place) == canonical
    if canonical:
        assert campus_place(canonical) == canonical


def test_event_place_keeps_2gis_for_street_addresses():
    url = "https://2gis.kz/almaty/geo/1"
    body = {"title": "Meetup", "startsAt": 1, "emoji": "party_popper_3d", "color": "#3B6BFF", "seats": None, "placeUrl": url}
    campus = clean_event({**body, "place": "Kazybek 1"})
    assert (campus["place"], campus["place_url"]) == ("\u041a\u0411 · 1 \u044d\u0442\u0430\u0436", None)
    street = clean_event({**body, "place": "Kazybek bi 12"})
    assert (street["place"], street["place_url"]) == ("Kazybek bi 12", url)
