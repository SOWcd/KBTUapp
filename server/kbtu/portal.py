"""A student's week of classes from the portal's own schedule page, saved on the phone and sent to the bot (PLAN 26,
owner Oct 25): Safari's "Web Archive" (a binary plist, the page in WebMainResource) or Chrome's "Download page" (an
.mht, MIME multipart, the page's HTML part UTF-8 with no charset). The page (uninet.kbtu.kz/student/schedule) holds the
whole week in its computer layout, hidden on a phone: a column per day, each class a block placed by its top and height
in pixels (an hour a fixed height from the first hour's label), with its kind as an icon's title, the course, the
teacher, the room, and for a long one its times. The student's name sits in the top bar ("Surname I."): the caller
checks it against the Microsoft one. The student ID on the page is never read. Only the standard library."""
from __future__ import annotations

import email
import plistlib
import re
from dataclasses import dataclass
from email import policy
from html.parser import HTMLParser


class NotSchedule(Exception):
    """Not a saved page, or a page without the week's grid."""


@dataclass
class Lesson:
    weekday: int        # 1 = Monday
    begins: str         # 'HH:MM'
    ends: str
    subject: str
    kind: str | None    # lecture / practice / lab
    room: str | None
    teacher: str | None
    code: str | None = None


def page_html(data: bytes) -> str:
    """The page's HTML from what the phone saved: a Web Archive, an .mht, or the page itself."""
    if data.startswith(b"bplist00"):
        try:
            main = plistlib.loads(data)["WebMainResource"]
            return bytes(main["WebResourceData"]).decode(str(main.get("WebResourceTextEncodingName") or "utf-8"), "replace")
        except (plistlib.InvalidFileException, KeyError, TypeError, LookupError, ValueError) as exc:
            raise NotSchedule("webarchive") from exc
    head = data[:2048].lower()
    if b"multipart/related" in head or b"mime-version" in head:
        msg = email.message_from_bytes(data, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                body = part.get_payload(decode=True) or b""
                try:
                    return body.decode(part.get_content_charset() or "utf-8", "replace")  # Chrome writes no charset: UTF-8
                except LookupError:
                    return body.decode("utf-8", "replace")
        raise NotSchedule("mht")
    if b"<html" in head or b"<!doctype" in head:
        return data.decode("utf-8", "replace")
    raise NotSchedule("format")


# ---------------------------------------------------------------- a small tree of the page (html.parser)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
        "path", "circle", "rect", "line", "polyline", "polygon", "use"}


class Node:
    __slots__ = ("tag", "cls", "style", "kids", "text", "up")

    def __init__(self, tag: str, attrs: dict, up: Node | None):
        self.tag, self.cls, self.style = tag, (attrs.get("class") or "").split(), attrs.get("style") or ""
        self.kids: list[Node] = []
        self.text: list[str] = []
        self.up = up

    def all(self):
        yield self
        for k in self.kids:
            yield from k.all()

    def words(self) -> str:
        """Its text and its children's, in order, one space between."""
        out: list[str] = []
        def walk(n: Node):
            out.extend(n.text)
            for k in n.kids:
                walk(k)
        walk(self)
        return " ".join(" ".join(out).split())

    def has(self, *cls: str) -> bool:
        return all(c in self.cls for c in cls)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.at = Node("#root", {}, None)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.at)
        self.at.kids.append(n)
        if tag not in VOID:
            self.at = n

    def handle_startendtag(self, tag, attrs):
        self.at.kids.append(Node(tag, dict(attrs), self.at))

    def handle_endtag(self, tag):
        n = self.at
        while n.up and n.tag != tag:
            n = n.up
        if n.up:  # a stray end tag closes nothing
            self.at = n.up

    def handle_data(self, data):
        if data.strip() and self.at.tag not in ("script", "style"):
            # a text after a child goes to an empty child of its own, so words() keeps the order
            if self.at.kids:
                t = Node("#text", {}, self.at)
                t.text.append(data)
                self.at.kids.append(t)
            else:
                self.at.text.append(data)


# ---------------------------------------------------------------- the week

DAYS = {**{d: i for i, d in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"), 1)},
        # Russian and Kazakh (the portal's other languages)
        **{d: i for i, d in enumerate(("\u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a", "\u0432\u0442\u043e\u0440\u043d\u0438\u043a",
                                       "\u0441\u0440\u0435\u0434\u0430", "\u0447\u0435\u0442\u0432\u0435\u0440\u0433", "\u043f\u044f\u0442\u043d\u0438\u0446\u0430",
                                       "\u0441\u0443\u0431\u0431\u043e\u0442\u0430", "\u0432\u043e\u0441\u043a\u0440\u0435\u0441\u0435\u043d\u044c\u0435"), 1)},
        **{d: i for i, d in enumerate(("\u0434\u04af\u0439\u0441\u0435\u043d\u0431\u0456", "\u0441\u0435\u0439\u0441\u0435\u043d\u0431\u0456",
                                       "\u0441\u04d9\u0440\u0441\u0435\u043d\u0431\u0456", "\u0431\u0435\u0439\u0441\u0435\u043d\u0431\u0456", "\u0436\u04b1\u043c\u0430",
                                       "\u0441\u0435\u043d\u0431\u0456", "\u0436\u0435\u043a\u0441\u0435\u043d\u0431\u0456"), 1)}}
KINDS = {"lecture": "lecture", "practice": "practice", "lab": "lab", "laboratory": "lab",
         "\u043b\u0435\u043a\u0446\u0438\u044f": "lecture", "\u043f\u0440\u0430\u043a\u0442\u0438\u043a\u0430": "practice",
         "\u043b\u0430\u0431\u043e\u0440\u0430\u0442\u043e\u0440\u043d\u0430\u044f": "lab", "\u0434\u04d9\u0440\u0456\u0441": "lecture",
         "\u0442\u04d9\u0436\u0456\u0440\u0438\u0431\u0435": "practice", "\u0437\u0435\u0440\u0442\u0445\u0430\u043d\u0430\u043b\u044b\u049b": "lab"}
LECTURE_OVER = 100  # minutes: a class with no label longer than this is a lecture (owner: lectures 2 h, practices 1 h, PE 1 h 40)
HHMM = re.compile(r"(\d{1,2}):(\d{2})")


def _px(style: str, key: str) -> float | None:
    m = re.search(rf"(?:^|;)\s*{key}\s*:\s*([\d.]+)px", style)
    return float(m[1]) if m else None


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Week:
    name: str | None        # as the top bar shows it, for the caller's check
    lessons: list[Lesson]


def parse(html: str) -> Week:
    """The week's classes from the schedule page. NotSchedule when there's no week grid on it."""
    p = _Tree()
    p.feed(html)
    p.close()
    nodes = list(p.root.all())
    name = next((n.words() for n in nodes if n.tag == "span" and n.has("text-sm", "md:block", "text-text-heading")), None)
    # the computer layout: a row of columns, the hours first (the phone's own shows one day)
    grid = next((n for n in nodes if n.has("flex") and any("min-w-[800px]" in c for c in n.cls)), None)
    if not grid:
        raise NotSchedule("grid")
    cols = [k for k in grid.kids if k.tag == "div"]
    hours = [n for n in cols[0].all() if HHMM.fullmatch(n.words()) and _px(n.style, "height")] if cols else []
    if not hours:
        raise NotSchedule("hours")
    m = HHMM.fullmatch(hours[0].words())
    base, per_hour = int(m[1]) * 60 + int(m[2]), _px(hours[0].style, "height") or 64.0
    out: list[Lesson] = []
    for i, col in enumerate(cols[1:], 1):
        title = next((n.words() for n in col.all() if n.has("text-sm", "font-medium")), "")
        day = DAYS.get(title.strip().lower(), i if i <= 7 else None)
        if not day:
            continue
        for b in col.all():
            top, height = _px(b.style, "top"), _px(b.style, "height")
            if not b.has("absolute") or top is None or height is None or not b.kids:
                continue
            head = next((n for n in b.kids if n.has("font-semibold")), None)
            if not head:
                continue
            label = next((n.words() for n in head.all() if n.tag == "title"), "")
            subject = " ".join(n.words() for n in head.kids if n.tag in ("span", "a", "#text")).strip()
            body = [n for n in b.kids if n.has("mt-0.5")]
            teacher = next((n.words() for n in body if n.has("text-text-body", "truncate")), None)
            room = next((n.words() for n in body if n.has("text-text-body") and not n.has("truncate")), None)
            shown = next((n.words() for n in body if n.has("text-text-muted")), "")
            times = HHMM.findall(shown)
            if len(times) == 2:  # its times as written beat the pixels
                begins, ends = (int(h) * 60 + int(mm) for h, mm in times)
            else:  # each block is its length less a 2 px gap
                begins = base + round(top / per_hour * 60)
                ends = begins + round((height + 2) / per_hour * 60)
            if not subject or ends <= begins:
                continue
            kind = KINDS.get(label.strip().lower()) or ("lecture" if ends - begins > LECTURE_OVER else "practice")
            out.append(Lesson(day, _hhmm(begins), _hhmm(ends), subject[:120], kind, (room or None) and room[:40], (teacher or None) and teacher[:80]))
    if not out:
        raise NotSchedule("empty")
    return Week(name, sorted(out, key=lambda x: (x.weekday, x.begins)))


def same_person(shown: str | None, first: str, last: str) -> bool:
    """The page's "Surname I." (or "Name S.", or the full name) is this student: a whole word is one of the names and an
    initial, if any, starts the other. Letters compared in Latin (a Cyrillic page against a Latin Microsoft name)."""
    from .logic import TRANSLIT
    norm = lambda s: re.sub(r"[^a-z]", "", s.lower().translate(TRANSLIT))  # noqa: E731
    words = [w for w in re.split(r"[\s,]+", shown or "") if w]
    full = [norm(w) for w in words if not w.endswith(".") and len(norm(w)) > 1]
    initials = [norm(w)[:1] for w in words if w.endswith(".") or len(norm(w)) == 1]
    names = {norm(first), norm(last)} - {""}
    if not full or not names or not set(full) & names:
        return False
    rest = names - set(full)
    return not initials or not rest or any(i and n.startswith(i) for i in initials for n in rest)
