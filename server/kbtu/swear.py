"""Swear words in a club's group (bot._swear, logic/chatmod.py): a word list, no AI, no network. find(text) gives the
matched stem from the lists below (what a hit stores), or None. Prefers missing a rare spelling over flagging an
innocent word: Russian stems count only at a word's start or after a known prefix ("na-", "po-", "za-" ...), so
"zastrakhuy" (insure!), "oskorblyat" (offend), "korablya", "khleb", "komanda" stay clean.

Each word is tried in a few spellings: lower case, look-alike Latin letters and digits folded into Cyrillic (and the
other way for the English list), Kazakh letters folded to their Russian twins, runs of the same letter squeezed (to one,
and runs of 3+ to two), single letters spaced or dotted apart joined ("b l y a"), one masked letter ("b*ya") tried as every letter.
The lists are \\u-escaped (the repo's hook keeps Cyrillic in the i18n files and texts.py); each line says it in Latin."""
from __future__ import annotations

import re
import unicodedata

# Russian prefixes a stem may follow ("na-khuy", "za-eb", "raz-ye-bat"); "s-" and "a-" are left out on purpose:
# "s-eb-e" (sebe, "oneself") and "a-suka" (the name Asuka) would match. "s-pizd" and "a-khue" are stems of their own.
PREFIXES = ("\u043d\u0430", "\u043f\u043e", "\u043d\u0438", "\u043d\u0435", "\u043e", "\u043e\u0431", "\u043e\u0431\u044a", "\u043e\u0442", "\u043e\u0442\u044a", "\u0437\u0430", "\u0432\u044b", "\u0434\u043e", "\u043f\u0440\u0438", "\u043f\u0440\u043e", "\u043f\u0435\u0440\u0435", "\u043f\u043e\u0434", "\u043f\u043e\u0434\u044a", "\u0440\u0430\u0437", "\u0440\u0430\u0437\u044a",
            "\u0440\u0430\u0441", "\u0441\u044a", "\u0441\u044c", "\u0438\u0437", "\u0438\u0437\u044a", "\u0432\u0437", "\u0432\u0437\u044a", "\u0432\u044a", "\u0443", "\u043d\u0435\u0434\u043e")

RU = (  # start of a word, or after a prefix
    "\u0431\u043b\u044f",      # blya, blyad, blyat
    "\u0445\u0443\u0439", "\u0445\u0443\u044f", "\u0445\u0443\u0435", "\u0445\u0443\u0438", "\u0445\u0443\u044e", "\u0430\u0445\u0443\u0435",  # khuy and its forms; a-khue
    "\u043f\u0438\u0437\u0434", "\u0441\u043f\u0438\u0437\u0434",  # pizd-, s-pizd-
    "\u0435\u0431\u0430", "\u0435\u0431\u043b", "\u0435\u0431\u0443", "\u0435\u0431\u043d", "\u0435\u0431\u043e", "\u0435\u0431\u0438\u0441\u044c", "\u0435\u0431\u0435\u0442",  # yeb- (never a bare "eb": "s-eb-e")
    "\u0434\u043e\u043b\u0431\u043e\u0435\u0431",  # dolboyob
    "\u0441\u0443\u043a\u0430", "\u0441\u0443\u043a\u0438", "\u0441\u0443\u043a\u0438\u043d",  # suka
    "\u043f\u0438\u0434\u043e\u0440", "\u043f\u0438\u0434\u0430\u0440", "\u043f\u0438\u0434\u0440",  # pidor
    "\u043c\u0443\u0434\u0430\u043a", "\u043c\u0443\u0434\u0430\u0447", "\u043c\u0443\u0434\u0438\u043b",  # mudak
    "\u0433\u0430\u043d\u0434\u043e\u043d", "\u0433\u043e\u043d\u0434\u043e\u043d",  # gandon
    "\u0448\u043b\u044e\u0445",     # shlyukh
    "\u0437\u0430\u043b\u0443\u043f",    # zalup
    "\u043c\u0430\u043d\u0434\u0430",    # manda
    # Kazakh, folded to Russian letters (q -> k, i -> i ...)
    "\u0441\u0438\u0433\u0435\u0439", "\u0441\u0438\u0433\u0435\u043c", "\u0441\u0438\u043a\u0442\u0438\u043c", "\u0441\u0438\u043a\u0442\u0438\u0440",  # sik-
    "\u043a\u043e\u0442\u0430\u043a",    # qotaq
    "\u043a\u0430\u043d\u0448\u044b\u043a",   # qanshyq
)
RU_WORDS = ("\u0435\u0431",)  # a word alone: "yob tvoyu"
# innocent words that hold a stem: a word containing one of these is clean
RU_ALLOW = ("\u0431\u043b\u044f\u0445", "\u0435\u0431\u043e\u043b",  # buckle, Ebola
            "\u043c\u0430\u043d\u0434\u0430\u0440\u0438\u043d", "\u043c\u0430\u043d\u0434\u0430\u0442", "\u043c\u0430\u043d\u0434\u0430\u043b",  # tangerine, mandate, mandala
            "\u0441\u0443\u043a\u0430\u0447",    # the surname Sukachev
            "\u043a\u043e\u0442\u0430\u043a\u0443",   # Kotaku
            "\u0431\u043b\u044f\u0448",    # blyashka (a plaque, a belt's badge)
            "\u0441\u0443\u043a\u0438\u044f", "\u0441\u0443\u043a\u0438\u044e", "\u0441\u0443\u043a\u0438\u044b",  # sukiyaki; Kazakh suqiyu (to poke, to stare)
            "\u043c\u0430\u043d\u0434\u0430\u0439",    # Kazakh mangday (forehead), folded
            "\u0437\u0430\u043c\u0430\u043d\u0434", "\u043e\u043c\u0430\u043d\u0434",  # Kazakh zamanda (in the era), zamandas (contemporary), Omanda (in Oman): za-/o- + manda
            "\u0441\u0443\u043a\u0430\u043d",  # Kazakh suqan (greedy-eyed), suqqan (poked), folded and squeezed
            "\u0441\u0443\u043a\u0438\u0430", "\u0441\u0443\u043a\u0430\u0440", "\u0441\u0443\u043a\u0430\u0435\u0432",  # the surnames Sukiasyan, Sukaev; Sukarno
            "\u0445\u0443\u0438\u0437")   # Huizinga
EN = ("fuck", "shit", "cunt", "bitch", "asshole", "dickhead", "whore", "slut", "nigger", "nigga", "faggot",
      "blyat", "blyad", "pizd")  # anywhere in a word; the last three: Russian in Latin letters
EN_WORDS = ("suka", "blya", "huj", "xuy", "nahuy", "nahui", "nahuj", "pohuy", "pohui", "pidor", "pidar", "mudak",
            "ebat", "yebat", "eblan")  # Russian in Latin letters, whole words only ("hui", "huy" alone: Chinese, Vietnamese names)
EN_ALLOW = ("scunthorp", "shiitak", "shitak", "niggard", "snigger", "kshiti", "ashita",  # Kshitij, Japanese "tomorrow"
            "ishit", "oshit", "shital")  # Japanese names (Kishitani, Nishitani, Yoshitomo), the Indian name Shital

# look-alikes: Latin and digits into Cyrillic, Kazakh into Russian; Cyrillic and digits into Latin
_TO_CYR = str.maketrans({**dict(zip("abcehkmnoprtxyi", "\u0430\u0432\u0441\u0435\u043d\u043a\u043c\u043f\u043e\u0440\u0433\u0442\u0445\u0443\u0438")), "0": "\u043e", "3": "\u0437", "4": "\u0447", "6": "\u0431", "@": "\u0430",
                         **dict(zip("\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456\u0451", "\u0430\u0433\u043a\u043d\u043e\u0443\u0443\u0445\u0438\u0435"))})
_TO_LAT = str.maketrans({**dict(zip("\u0430\u0432\u0441\u0435\u043d\u043a\u043c\u043e\u0440\u0442\u0445\u0443", "abcehkmoptxy")), "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
                         "@": "a", "$": "s"})
_GONE = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\u2060\ufeff\u0301\u0300"))  # soft hyphen, zero widths, accents
_WORD = re.compile(r"(?:[^\W_]|[@$*])+")  # letters and digits; @ $ * count inside a word
_RUN2, _RUN3 = re.compile(r"(.)\1+"), re.compile(r"(.)\1{2,}")
_ASCII = re.compile(r"[a-z]")
_CYR = re.compile(r"[\u0400-\u04ff]")


def _stems(words: tuple, prefix: bool) -> re.Pattern:
    alt = "|".join(sorted(map(re.escape, words), key=len, reverse=True))
    pre = "|".join(sorted(map(re.escape, PREFIXES), key=len, reverse=True))
    return re.compile(f"^(?:{pre})?({alt})" if prefix else f"({alt})")


_RU, _EN = _stems(RU, True), _stems(EN, False)


def _words(text: str) -> list[str]:
    """The words; three or more single letters split by spaces or dots ("b l y a", "b.l.y.a") joined into one. Two
    are initials ("Ahmetova E.B."), not a word."""
    text = unicodedata.normalize("NFKC", text).translate(_GONE).lower()
    out: list[str] = []
    single, last = "", 0  # a run of one-letter words, where the last word ended
    for m in _WORD.finditer(text):
        w, near = m.group(), m.start() - last <= 3
        last = m.end()
        if len(w) == 1 and (near or not single):
            single += w
            continue
        out += [single] if len(single) > 2 else []
        single = w if len(w) == 1 else ""
        out += [] if single else [w]
    return out + ([single] if len(single) > 2 else [])


def _spellings(w: str) -> set[str]:
    w = w.strip("*")
    if w.count("*") > 1:
        return set()
    forms = {_RUN2.sub(r"\1", w), _RUN3.sub(r"\1\1", w)}
    if "*" in w and len(w) >= 3:  # one masked letter: every letter in its place
        forms = {f.replace("*", c) for f in forms for c in "\u0430\u0431\u0432\u0433\u0434\u0435\u0436\u0437\u0438\u0439\u043a\u043b\u043c\u043d\u043e\u043f\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044a\u044b\u044c\u044d\u044e\u044fabcdefghijklmnopqrstuvwxyz"}
    return forms


def find(text: str) -> str | None:
    """The first stem a word of the text holds, or None."""
    for w in _words(str(text or "")):
        for f in _spellings(w):
            cyr, lat = f.translate(_TO_CYR), f.translate(_TO_LAT)
            # Russian only for a word all Cyrillic once folded ("cyka" is; "oxyester" isn't), English only for one
            # with no Cyrillic left: an English word never folds into a Russian stem by chance, nor the other way
            if not _ASCII.search(cyr) and not any(a in cyr for a in RU_ALLOW):
                if cyr in RU_WORDS:
                    return cyr
                if m := _RU.match(cyr):
                    return m.group(1)
            if not _CYR.search(lat) and not any(a in lat for a in EN_ALLOW):
                if lat in EN_WORDS:
                    return lat
                if m := _EN.search(lat):
                    return m.group(1)
    return None
