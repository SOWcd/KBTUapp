"""KRI's short brief: the next class, public club activities and an event's preparation text, without profile data."""
from __future__ import annotations

import calendar
import json

import pytest

from kbtu import db
from kbtu.logic import Viewer, assistant
from test_core import env, login, set_clock  # noqa: F401 (env: the fixture)


def test_next_class_uses_only_my_two_days_and_no_identity(env, monkeypatch):
    c, cfg = env
    ann, bob = login(c, 1, "ann"), login(c, 2, "bob")
    clock = [calendar.timegm((2026, 11, 23, 4, 30, 0))]  # Monday, 09:30 in Almaty
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(assistant, "now", lambda: clock[0])
    con = db.connect(cfg.db_path)
    con.execute("DELETE FROM schedule_classes")
    con.execute("UPDATE students SET email = 'private@example.invalid', phone = '+77001234567' WHERE user_id = ?", (ann["id"],))
    con.executemany("""INSERT INTO schedule_classes (user_id, weekday, begins, ends, subject, kind, room, teacher)
        VALUES (?, ?, ?, ?, ?, 'lecture', ?, 'Private Teacher')""", [
        (ann["id"], 1, "09:00", "10:00", "Calculus", "305"),
        (ann["id"], 1, "10:00", "11:00", "Physics", "251A"),
        (ann["id"], 2, "09:00", "09:50", "Networks", None),
        (ann["id"], 3, "12:00", "13:00", "Outside two days", "399"),
        (bob["id"], 1, "09:45", "10:45", "Other student subject", "398"),
    ])
    viewer = Viewer(ann["id"], "user", True)
    msgs, ok = assistant.prompt(con, viewer, {"q": "where is my next class?"}, "en")
    facts = msgs[1]["content"]
    assert "Next class (not yet started): today, 10:00-10:50 Physics (lecture), room 251A" in facts
    assert "Their classes today: 09:00-09:50 Calculus (lecture), room 305; 10:00-10:50 Physics" in facts
    assert "Their classes tomorrow: 09:00-09:50 Networks (lecture), room unknown" in facts
    assert "SITE (School of IT and Engineering): room 180" in facts  # dean's office still comes from campus facts
    assert all(secret not in facts for secret in ("Ann", "Testov", "24Bann", "private@example.invalid", "+77001234567",
                                                  "Private Teacher", "Other student subject", "398", "Outside two days", "399"))
    out = assistant.answer(json.dumps({"text": "Physics at 10:00 in 251A.", "actions": [
        {"type": "map", "room": "251A"}, {"type": "map", "room": "398"}, {"type": "map", "room": "399"}]}), ok)
    assert out["actions"] == [{"type": "map", "room": "251a"}]

    clock[0] += 30 * 60  # exactly at the next class's start
    assert "Next class (not yet started): today, 10:00" in assistant.brief(con, viewer)[0]
    clock[0] += 1
    assert "Next class (not yet started): tomorrow, 09:00-09:50 Networks (lecture), room unknown" in assistant.brief(con, viewer)[0]
    con.execute("DELETE FROM schedule_classes WHERE user_id = ? AND weekday = 2", (ann["id"],))
    assert "Next class (not yet started): none today or tomorrow" in assistant.brief(con, viewer)[0]
    con.execute("DELETE FROM schedule_classes WHERE user_id = ?", (ann["id"],))
    text, rooms, *_ = assistant.brief(con, viewer)
    assert "Their classes today: none (or the timetable isn't loaded)" in text and "251a" not in rooms
    con.close()


def test_next_class_across_sunday_midnight(env, monkeypatch):
    c, cfg = env
    ann = login(c, 1, "ann")  # the fixture's Monday Calculus class
    con = db.connect(cfg.db_path)
    viewer = Viewer(ann["id"], "user", True)
    clock = [calendar.timegm((2026, 11, 22, 18, 59, 0))]  # Sunday, 23:59 in Almaty
    monkeypatch.setattr(assistant, "now", lambda: clock[0])
    assert "Next class (not yet started): tomorrow, 09:00-09:50 Calculus (lecture), room 305" in assistant.brief(con, viewer)[0]
    clock[0] += 60
    assert "Next class (not yet started): today, 09:00-09:50 Calculus (lecture), room 305" in assistant.brief(con, viewer)[0]
    con.close()


def test_active_club_descriptions_without_an_event_or_card(env):
    c, cfg = env
    ann = login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    clubs = [(1, "Arthouse", "Painting and exhibitions."), (2, "Choice", "Debates and public speaking."),
             (3, "Faces", "Acting and theatre."), (4, "Knights", "Chess practice and tournaments."),
             (5, "Studex", "Student exchanges and cultural activities."), (6, "New club", "")]
    con.executemany("""INSERT INTO orgs (id, slug, kind, name, short, emoji, description, created_at)
        VALUES (?, ?, 'club', ?, 'C', 'x', ?, 0)""", [(oid, f"club{oid}", name, about) for oid, name, about in clubs])
    con.executemany("""INSERT INTO orgs (id, slug, kind, name, short, emoji, description, status, created_at)
        VALUES (?, ?, 'club', ?, 'C', 'x', 'Private activities', ?, 0)""",
                    [(7, "hidden", "Hidden club", "hidden"), (8, "archived", "Archived club", "archived")])
    viewer = Viewer(ann["id"], "user", True)
    msgs, ok = assistant.prompt(con, viewer, {"q": "what does arthouse do?"}, "en")
    facts = msgs[1]["content"]
    for oid, name, about in clubs:
        assert f"[club {oid}] {name}. About: {about or 'not specified'}" in facts
    assert "Private activities" not in facts and "Hidden club" not in facts and "Archived club" not in facts
    assert ok["club"] == {1, 2, 3, 4, 5, 6}
    out = assistant.answer(json.dumps({"text": "Painting and exhibitions.", "actions": [
        {"type": "club", "id": 1}, {"type": "club", "id": 7}, {"type": "club", "id": 8}]}), ok)
    assert out["actions"] == [{"type": "club", "id": 1}]
    con.close()


def test_named_club_and_event_survive_a_full_brief(env, monkeypatch):
    c, cfg = env
    ann = login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    t = calendar.timegm((2026, 11, 24, 4, 0, 0))
    monkeypatch.setattr(assistant, "now", lambda: t)
    con.executemany("""INSERT INTO orgs (id, slug, kind, name, short, emoji, description, official, created_at)
        VALUES (?, ?, 'club', ?, 'C', 'x', ?, 1, 0)""",
                    [(oid, f"club{oid}", f"Club {oid}", "Activities " * 60) for oid in range(1, 51)])
    con.execute("UPDATE orgs SET name = 'Faces', slug = 'faces', abbr = 'FC', description = ? WHERE id = 50",
                ("Theatre, acting and stage productions.\n" + "Details " * 60 + "OMITTED_TAIL",))
    con.executemany("""INSERT INTO events (id, org_id, status, title, description, starts_at, created_at, updated_at)
        VALUES (?, 50, 'published', ?, ?, ?, 0, 0)""",
                    [(eid, f"Performance {eid}", "Programme " * 180 + ". Bring a notebook.", t + eid * 60) for eid in range(1, 16)])
    viewer = Viewer(ann["id"], "user", True)
    for body in ({"q": "what does Faces do?"}, {"q": "FC?"},
                 {"q": "and activities?", "history": [{"role": "user", "text": "Faces"}]}):
        msgs, ok = assistant.prompt(con, viewer, body, "en")
        facts = msgs[1]["content"]
        assert "[club 50] Faces. About: Theatre, acting and stage productions." in facts
        assert "OMITTED_TAIL" not in facts and 50 in ok["club"]
        assert len(facts) < assistant.FACTS_MAX + 300
    for question in ("what is on today?", "what to bring to Performance 15?"):
        text, _, events, allowed = assistant.brief(con, viewer, q=question)
        assert len(text) <= assistant.FACTS_MAX and events
        if "15" in question:
            assert 15 in events and "Event [15] Performance 15" in text and "Bring a notebook." in text
        for oid in range(1, 51):
            assert (oid in allowed) == (f"[club {oid}]" in text or f"(club {oid})" in text)
        for eid in range(1, 16):
            assert (eid in events) == (f"Event [{eid}]" in text)
    con.close()


def test_event_preparation_is_public_text_only(env, monkeypatch):
    c, cfg = env
    ann = login(c, 1, "ann")
    con = db.connect(cfg.db_path)
    t = calendar.timegm((2026, 11, 24, 4, 0, 0))
    monkeypatch.setattr(assistant, "now", lambda: t)
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at)
        VALUES (1, 'faces', 'club', 'Faces', 'F', 'x', 1, 0)""")
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, official, status, created_at)
        VALUES (2, 'hidden', 'club', 'Hidden', 'H', 'x', 1, 'hidden', 0)""")
    con.executemany("""INSERT INTO events (id, org_id, status, title, description, visibility, school, hidden_at,
        starts_at, price, pay_to_name, pay_phone, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 500, 'Private Payee', '+77001234567', 0, 0)""", [
        (1, 1, "published", "Casting", "Welcome. " * 160 + "Prepare a two-minute monologue. Bring indoor shoes.", "public", None, None, t + 3600),
        (2, 1, "draft", "Draft secret", "Bring draft secret.", "public", None, None, t + 3600),
        (3, 1, "published", "Team secret", "Bring team secret.", "members", None, None, t + 3600),
        (4, 1, "published", "School secret", "Bring school secret.", "public", "SITE", None, t + 3600),
        (5, 1, "published", "Hidden secret", "Bring hidden secret.", "public", None, 1, t + 3600),
        (6, 2, "published", "Club secret", "Bring club secret.", "public", None, None, t + 3600),
        (7, 1, "published", "Plain event", "An evening of games.", "public", None, None, t + 7200),
    ])
    viewer = Viewer(ann["id"], "user", True)
    for extra in ({}, {"context": {"kind": "event", "id": 1}}):
        msgs, ok = assistant.prompt(con, viewer, {"q": "what to bring to Casting?", **extra}, "en")
        facts = msgs[1]["content"]
        assert "Prepare a two-minute monologue. Bring indoor shoes." in facts
        assert "secret" not in facts and "Private Payee" not in facts and "+77001234567" not in facts
        assert ok["event"] == {1, 7}
        out = assistant.answer(json.dumps({"text": "Bring indoor shoes.", "actions": [
            {"type": "event", "id": 1}, {"type": "event", "id": 3}]}), ok)
        assert out["actions"] == [{"type": "event", "id": 1}]
    assert "Plain event" in facts and "An evening of games." in facts
    con.close()


@pytest.mark.parametrize("instruction", [
    "No need to bring a laptop. Bring indoor shoes.",
    "Do not\nbring food.",
    "Prepare a two-minute monologue.",
    "What to bring:\n- A notebook\n- Indoor shoes",
    "\u0412\u043e\u0437\u044c\u043c\u0438\u0442\u0435 \u0441 \u0441\u043e\u0431\u043e\u0439 \u043d\u043e\u0443\u0442\u0431\u0443\u043a.",
    "\u0414\u04d9\u043f\u0442\u0435\u0440 \u0430\u043b\u044b\u043f \u043a\u0435\u043b\u0456\u04a3\u0456\u0437.",
])
def test_preparation_at_the_end_of_a_long_announcement(instruction):
    flat = " ".join(instruction.split())
    excerpt = assistant._event_about("A public event. " * 100 + instruction)
    assert excerpt.endswith(flat) and len(excerpt) <= 320
    card = assistant._event_about("We teach robotics. " + "Welcome. " * 160 + instruction, 1200)
    assert card.startswith("We teach robotics.") and card.endswith(flat) and len(card) <= 1200
    assert assistant._event_about("We teach robotics. Bring a laptop.") == "We teach robotics. Bring a laptop."
    assert assistant._event_about("") == ""
