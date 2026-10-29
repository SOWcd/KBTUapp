"""The students' assistant (Oct 30, the owner: a student asks the app "where is my dean's office?" and it answers,
knowing their school, course, timetable, the campus and what's on). One question at a time with the last few turns;
the server hands the model a short brief of facts and takes back JSON: the words and up to three buttons (a room on
the map, an event), each checked against the brief so nothing made up opens. Sent to the model: the school, the
course, this and the next day's classes (subject, time, room), the coming public events and the campus places; never
the name, student ID, mail or phone. Only the EU host the privacy policy names. Kept: a count per day (30), not the
questions."""
from __future__ import annotations

import json
import re
import time

from .core import ApiError, Viewer, need_student, now, one, rows

A_DAY = 30
TURNS = 6                 # the last turns sent along (a follow-up "and where is it?" needs the one before)
Q_MAX = 300
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# the campus's named places with their rooms (the map's own list, web/src/lib/map.ts SPOTS); a room's first digit is
# its floor, a one- or two-digit room is in the basement (floor 0)
PLACES = (("Canteen", "the basement, floor 0"), ("Library", "158"), ("Career Center", "152"), ("Student services", "155"),
          ("Halyk Co-working", "floor 1, the middle block"), ("Kunaev auditorium", "400a"), ("Al-Farabi hall", "470"),
          ("Independence hall", "floor 2"), ("Gamedev lab", "47"), ("Honeywell lab", "140"), ("Security", "250a"),
          ("Dispatcher", "1"), ("Rector", "466"), ("Vice-rector for science", "415"), ("Vice-rector for social affairs", "472"),
          ("Legal department", "503"), ("Accounting", "523"))
# the schools' offices the UNI-Q plan names (the dean's office of the others isn't known: the assistant says so)
SCHOOL_ROOMS = {"SITE": ("School of IT and Engineering", "180"), "SEOGI": ("School of Energy and Petroleum Industry", "356"),
                "KMA": ("Kazakhstan Maritime Academy", "255")}
ROOM = re.compile(r"^\d{1,3}[a-c]?$")
LANGS = {"ru": "Russian", "kk": "Kazakh", "en": "English"}

SYSTEM = """You are the assistant inside KBTU App, a Telegram mini app for students of KBTU (Kazakh-British Technical
University, Almaty, Tole bi 59). Answer the student briefly (1-4 sentences), warmly, in {lang}. Use only the facts
below. If they don't hold the answer, say plainly you don't know and suggest where to ask (Student services, room
155, or their school's office); never invent a room, a time, a person or a rule. A room's first digit is its floor.
Reply with JSON only, no other text:
{{"text": "...", "actions": [{{"type": "map", "room": "180"}}, {{"type": "event", "id": 12}}]}}
actions: at most 3, only for rooms or event ids that appear in the facts and help with this question; [] if none.

FACTS
{facts}"""


def _school(code: str | None) -> str:
    if not code:
        return "unknown"
    known = SCHOOL_ROOMS.get(code.upper())
    return f"{code} ({known[0]})" if known else code


def brief(con, v: Viewer) -> tuple[str, set[str], set[int]]:
    """The facts for this student (and the rooms and events a button may open)."""
    s = one(con, "SELECT school, course FROM students WHERE user_id = ?", v.id)
    t = now()
    local = time.gmtime(t + 5 * 3600)
    lines = [f"Now: {WEEKDAYS[local.tm_wday]}, {time.strftime('%d %B %Y, %H:%M', local)} (Almaty).",
             f"The student: school {_school(s['school'] if s else None)}, year {s['course'] if s and s['course'] else 'unknown'}."]
    rooms: set[str] = set()
    for label, wd in (("today", local.tm_wday + 1), ("tomorrow", local.tm_wday % 7 + 1)):
        cls = rows(con, "SELECT begins, ends, subject, kind, room FROM schedule_classes WHERE user_id = ? AND weekday = ? ORDER BY begins", v.id, wd)
        lines.append(f"Their classes {label}: " + ("; ".join(f"{c['begins']}-{c['ends']} {c['subject']}{' (' + c['kind'] + ')' if c['kind'] else ''}"
                                                              f"{', room ' + c['room'] if c['room'] else ''}" for c in cls) or "none (or the timetable isn't loaded)"))
        rooms |= {c["room"] for c in cls if c["room"]}
    lines.append("Campus places: " + "; ".join(f"{n}: room {r}" if ROOM.match(r) else f"{n}: {r}" for n, r in PLACES))
    rooms |= {r for _, r in PLACES if ROOM.match(r)}
    lines.append("Schools' offices on the plan: " + "; ".join(f"{k} ({n}): room {r}" for k, (n, r) in SCHOOL_ROOMS.items())
                 + ". Other schools' dean's offices: unknown.")
    rooms |= {r for _, r in SCHOOL_ROOMS.values()}
    evs = rows(con, """SELECT e.id, e.title, e.starts_at, e.place, o.name AS org FROM events e JOIN orgs o ON o.id = e.org_id
        WHERE e.status = 'published' AND e.visibility = 'public' AND e.hidden_at IS NULL AND o.status != 'hidden'
          AND e.starts_at BETWEEN ? AND ? ORDER BY e.starts_at LIMIT 15""", t - 3 * 3600, t + 7 * 86400)
    lines.append("Coming events (id, title, when, where, by): " + ("; ".join(
        f"[{e['id']}] {e['title']}, {time.strftime('%a %d %b %H:%M', time.gmtime(e['starts_at'] + 5 * 3600))}, {e['place'] or 'place to be announced'}, {e['org']}"
        for e in evs) or "none this week"))
    return "\n".join(lines), rooms, {e["id"] for e in evs}


def prompt(con, v: Viewer, body: dict, lang: str) -> tuple[list[dict], set[str], set[int]]:
    """The messages for the model, after the day's allowance (counted here, before the model is asked)."""
    need_student(v)
    q = " ".join(str(body.get("q") or "").split())
    past = body.get("history") or []
    if not 2 <= len(q) <= Q_MAX or not isinstance(past, list):
        raise ApiError("bad_input")
    if one(con, "SELECT COUNT(*) FROM assist_uses WHERE user_id = ? AND at > ?", v.id, now() - 86400)[0] >= A_DAY:
        raise ApiError("rate_limited", "assistant")
    con.execute("INSERT INTO assist_uses (user_id, at) VALUES (?, ?)", (v.id, now()))
    facts, rooms, events = brief(con, v)
    msgs = [{"role": "system", "content": SYSTEM.format(lang=LANGS.get(lang, "Russian"), facts=facts)}]
    for m in past[-TURNS:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("text"), str):
            msgs.append({"role": m["role"], "content": m["text"][:Q_MAX * 2]})
    msgs.append({"role": "user", "content": q})
    return msgs, rooms, events


def _json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        x = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    return x if isinstance(x, dict) and isinstance(x.get("text"), str) and x["text"].strip() else None


def usable(text: str) -> bool:
    return _json(text) is not None


def answer(text: str, rooms: set[str], events: set[int]) -> dict:
    """The model's JSON, its buttons kept only where the brief had them (nothing invented opens)."""
    x = _json(text) or {"text": text.strip()[:600], "actions": []}
    acts = []
    for a in x.get("actions") or []:
        if not isinstance(a, dict):
            continue
        if a.get("type") == "map" and str(a.get("room", "")).lower() in rooms:
            acts.append({"type": "map", "room": str(a["room"]).lower()})
        elif a.get("type") == "event" and isinstance(a.get("id"), int) and a["id"] in events:
            acts.append({"type": "event", "id": a["id"]})
    return {"text": x["text"].strip()[:1200], "actions": acts[:3]}


def sweep(con) -> None:
    con.execute("DELETE FROM assist_uses WHERE at < ?", (now() - 2 * 86400,))
