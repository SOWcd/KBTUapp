"""The one search folds Kazakh letters to the Russian ones a Russian keyboard types (owner, Nov 12)."""
from kbtu.logic import search


def test_kazakh_name_by_russian_letters():
    name = "\u04d8\u0441\u0435\u043b \u049a\u0430\u0439\u0440\u0430\u0442\u04b1\u043b\u044b"  # Kazakh spelling
    assert search.hit(search.fold("\u0430\u0441\u0435\u043b \u043a\u0430\u0439\u0440\u0430\u0442\u0443\u043b\u044b"), [name])  # typed in Russian
    assert search.hit(search.fold("\u04d9\u0441\u0435\u043b"), [name])  # and in Kazakh still
    assert not search.hit(search.fold("\u0431\u0435\u043a"), [name])
