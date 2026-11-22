"""The server and web assign the same search scores for layouts, spellings and typos."""
import pytest

from kbtu.logic import search


def test_kazakh_name_by_russian_letters():
    name = "\u04d8\u0441\u0435\u043b \u049a\u0430\u0439\u0440\u0430\u0442\u04b1\u043b\u044b"  # Kazakh spelling
    assert search.hit(search.fold("\u0430\u0441\u0435\u043b \u043a\u0430\u0439\u0440\u0430\u0442\u0443\u043b\u044b"), [name])  # typed in Russian
    assert search.hit(search.fold("\u04d9\u0441\u0435\u043b"), [name])  # and in Kazakh still
    assert not search.hit(search.fold("\u0431\u0435\u043a"), [name])


aigerim = '\u0410\u0439\u0433\u0435\u0440\u0438\u043c'
asel = '\u04d8\u0441\u0435\u043b'
qazaq = '\u049a\u0430\u0437\u0430\u049b'
zhansaya = '\u0416\u0430\u043d\u0441\u0430\u044f'

_CASES = [
    ('FQUTHBV', aigerim, 2),
    ('fqutqhbv', aigerim, 1),
    ('\u0444\u0448\u043f\u0443\u043a\u0448\u044c', 'Aigerim', 2),
    (';tyz', '\u0416\u0435\u043d\u044f', 2),
    (':tyz', '\u0416\u0435\u043d\u044f', 2),
    ('2ctk', asel, 2),
    ('2\u0441\u0435\u043b', asel, 2),
    ('@ctk', asel, 2),
    ('2', asel, 0),
    ('0fpf0', qazaq, 2),
    ('\u0441\u0434\u0433\u0438\u04d9\u04a3', 'Club24', 2),
    ('\u0430\u0441\u0435\u043b', asel, 3),
    ('aigerim', aigerim, 2),
    ('jansa', zhansaya, 2),
    (zhansaya, 'Zhansaya Smail', 2),
    ('Maria', '\u041c\u0430\u0440\u0438\u044f', 2),
    ('\u042e\u043b\u0438\u044f', 'Iulia', 2),
    ('Yelena', '\u0415\u043b\u0435\u043d\u0430', 2),
    ('Mikhail', '\u041c\u0438\u0445\u0430\u0438\u043b', 2),
    ('Shevchenko', '\u0428\u0435\u0432\u0447\u0435\u043d\u043a\u043e', 2),
    ('Shchuka', '\u0429\u0443\u043a\u0430', 2),
    ('Tsarev', '\u0426\u0430\u0440\u0451\u0432', 2),
    ('Shyngys', '\u0428\u044b\u04a3\u0493\u044b\u0441', 2),
    ('Ghalym', '\u0492\u0430\u043b\u044b\u043c', 2),
    ('\u00d6rken', '\u04e8\u0440\u043a\u0435\u043d', 2),
    ('Q\u016brman\u011fazy', '\u049a\u04b1\u0440\u043c\u0430\u043d\u0493\u0430\u0437\u044b', 2),
    ('Sattpayyeva', 'Satpayeva', 2),
    ('Satpeva', 'Aigerim Satpayeva', 1),
    ('Agierim', 'Aigerim', 1),
    ('Nightmra', 'Nightmare on Tole Bi', 1),
    ('xathom', 'Phantom', 0),
    ('xathomzz', 'Phantomize', 0),
    ('xhanxomi', 'Phantomize', 1),
    ('xhanxomixati', 'Phantomization', 1),
    ('Ivax', 'Aigerim Satpayeva', 0),
    ('Ajg', 'Aigerim', 0),
    ('24bal0001', '24bal0002', 0),
    ('CS100', 'CS101', 0),
    ('b', 'IT Club', 0),
    ('ai', 'Aigerim', 3),
    ('STRASSE', 'Stra\u00dfe', 3),
    ('rjytw-2ctk', '\u043a\u043e\u043d\u0435\u0446 \u04d8\u0441\u0435\u043b', 2),
    ('bi-tole', 'A Nightmare on Tole Bi Street', 3),
    (';', 'Chess', 0),
]

@pytest.mark.parametrize("q,name,expected", _CASES)
def test_search_score(q, name, expected):
    assert search.score(q, [name]) == expected
    assert search.hit(q, [name]) == (expected > 0)


def test_scoring_multiple_aliases():
    assert search.score("satp fquthbv", [f"{aigerim} Satpayeva"]) == 2
    assert search.score("satp fqutqhbv", [f"{aigerim} Satpayeva"]) == 1
    assert search.score("satp fquthbv", [aigerim, "Satpayeva"]) == 0
    assert search.score("aigerim", ["Aigerm", aigerim, "Aigerim Satpayeva"]) == 3
    assert search.score("aigerim", [None, ""]) == 0
    assert search.score("  ", ["Aigerim"]) == 0
