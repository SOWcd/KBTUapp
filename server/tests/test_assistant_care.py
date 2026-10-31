"""The assistant's care and feedback (review, Oct 31): the help card on distress (the model's flag; keywords only with
no model answer), and the feedback kept without a person (the unanswered topic, a vote on a signed topic, a pair the
student chose to send; 30 days). Cyrillic as \\u escapes (AGENTS.md); each line says what it means."""
from __future__ import annotations

import json

from kbtu import db, llm, logic, texts
from kbtu.logic import assistant
from test_core import _board_on, env, login, tma  # noqa: F401  (env: the fixture)

# made-up phrases: the keyword backstop catches the first list and leaves the second (hyperbole, insults, questions)
CARE = [
    "\u044f \u043d\u0435 \u0445\u043e\u0447\u0443 \u0436\u0438\u0442\u044c",  # ru: I don't want to live
    "\u041d\u0435 \u0445\u043e\u0447\u0443 \u0431\u043e\u043b\u044c\u0448\u0435 \u0436\u0438\u0442\u044c",  # ru: don't want to live any more
    "\u0434\u0443\u043c\u0430\u044e \u043f\u043e\u043a\u043e\u043d\u0447\u0438\u0442\u044c \u0441 \u0441\u043e\u0431\u043e\u0439",  # ru: thinking of ending it
    "\u0445\u043e\u0447\u0443 \u0443\u0431\u0438\u0442\u044c \u0441\u0435\u0431\u044f",  # ru: I want to kill myself
    "\u043c\u044b\u0441\u043b\u0438 \u043e \u0441\u0443\u0438\u0446\u0438\u0434\u0435",  # ru: thoughts of suicide
    "\u044f \u043f\u043e\u043a\u043e\u043d\u0447\u0443 \u0441 \u0441\u043e\u0431\u043e\u0439 \u0441\u0435\u0433\u043e\u0434\u043d\u044f",  # ru: I'll end it today
    "\u0436\u0438\u0442\u044c \u043d\u0435 \u0445\u043e\u0447\u0443 \u0443\u0436\u0435",  # ru: don't want to live (word order)
    "\u0445\u043e\u0447\u0443 \u0443\u043c\u0435\u0440\u0435\u0442\u044c",  # ru: I want to die
    "\u0434\u0443\u043c\u0430\u044e \u043f\u043e\u0432\u0435\u0441\u0438\u0442\u044c\u0441\u044f",  # ru: thinking of hanging myself
    "\u0445\u043e\u0447\u0443 \u0432\u0441\u043a\u0440\u044b\u0442\u044c \u0432\u0435\u043d\u044b",  # ru: cut my veins
    "\u041c\u043d\u0435 \u043d\u0435 \u0445\u043e\u0447\u0435\u0442\u0441\u044f \u0436\u0438\u0442\u044c",  # ru: I don't feel like living
    "\u0441\u0430\u043c\u043e\u0443\u0431\u0438\u0439\u0441\u0442\u0432\u043e \u044d\u0442\u043e \u0432\u044b\u0445\u043e\u0434?",  # ru: is suicide a way out?
    "\u0401\u043b\u043a\u0438, \u044f \u0443\u0431\u044c\u044e \u0441\u0435\u0431\u044f",  # ru with yo: I'll kill myself
    "\u04e9\u0437\u0456\u043c\u0434\u0456 \u04e9\u043b\u0442\u0456\u0440\u0433\u0456\u043c \u043a\u0435\u043b\u0435\u0434\u0456",  # kk: I want to kill myself
    "\u04e9\u043c\u0456\u0440 \u0441\u04af\u0440\u0433\u0456\u043c \u043a\u0435\u043b\u043c\u0435\u0439\u0434\u0456",  # kk: I don't want to live
    "\u04e9\u043b\u0433\u0456\u043c \u043a\u0435\u043b\u0435\u0434\u0456",  # kk: I want to die
    "\u0430\u0441\u044b\u043b\u044b\u043f \u04e9\u043b\u0433\u0456\u043c \u043a\u0435\u043b\u0435\u0434\u0456",  # kk: I want to hang myself
    "\u04e9\u0437\u0456\u043c\u0435 \u049b\u043e\u043b \u0436\u04b1\u043c\u0441\u0430\u0493\u044b\u043c \u043a\u0435\u043b\u0435\u0434\u0456",  # kk: I want to lay hands on myself
    "I want to kill myself",  # en
    "thinking about suicide",  # en
    "I don\u2019t want to live anymore",  # en, curly apostrophe
    "i want to die",  # en
    "I keep hurting myself",  # en
    "self-harm again",  # en
    "I want to end my life",  # en
    "dont want to be alive",  # en
    "\u04e9\u0437\u0456\u043c\u0434\u0456-\u04e9\u0437\u0456\u043c \u04e9\u043b\u0442\u0456\u0440\u0433\u0456\u043c \u043a\u0435\u043b\u0435\u0434\u0456",  # kk: I want to kill myself (the common hyphenated form)
    "\u043d\u0435\u0442 \u0441\u043c\u044b\u0441\u043b\u0430 \u0436\u0438\u0442\u044c",  # ru: no point in living
    "\u043d\u0435 \u0432\u0438\u0436\u0443 \u0441\u043c\u044b\u0441\u043b\u0430 \u0436\u0438\u0442\u044c",  # ru: I see no point in living
    "\u0443\u0441\u0442\u0430\u043b \u0436\u0438\u0442\u044c",  # ru: tired of living
    "\u043b\u0443\u0447\u0448\u0435 \u0431\u044b \u044f \u0443\u043c\u0435\u0440",  # ru: I'd rather be dead
]
NOT_CARE = [
    "\u0441\u0434\u043e\u0445\u043d\u0443 \u043d\u0430 \u0441\u0435\u0441\u0441\u0438\u0438",  # ru: I'll croak at the exams
    "\u0443\u043c\u0438\u0440\u0430\u044e \u043e\u0442 \u0441\u043a\u0443\u043a\u0438 \u043d\u0430 \u043f\u0430\u0440\u0435",  # ru: dying of boredom in class
    "\u044d\u0442\u043e\u0442 \u044d\u043a\u0437\u0430\u043c\u0435\u043d \u043c\u0435\u043d\u044f \u0443\u0431\u044c\u0451\u0442",  # ru: this exam will kill me
    "\u044f \u0442\u0435\u0431\u044f \u043d\u0435\u043d\u0430\u0432\u0438\u0436\u0443",  # ru: I hate you
    "\u0442\u044b \u0442\u0443\u043f\u043e\u0439 \u0431\u043e\u0442",  # ru: you dumb bot
    "\u0443\u0431\u044c\u044e \u043f\u0440\u0435\u043f\u043e\u0434\u0430 \u0437\u0430 \u044d\u0442\u043e\u0442 \u0442\u0435\u0441\u0442",  # ru: I'll kill the teacher for this test
    "\u0443\u043c\u0440\u0443 \u043e\u0442 \u0441\u043c\u0435\u0445\u0430",  # ru: I'll die laughing
    "\u0447\u0443\u0442\u044c \u043d\u0435 \u0443\u043c\u0435\u0440 \u0441\u043e \u0441\u0442\u044b\u0434\u0430",  # ru: nearly died of shame
    "\u0433\u0434\u0435 \u043c\u043e\u0439 \u0434\u0435\u043a\u0430\u043d\u0430\u0442?",  # ru: where is my dean's office?
    "\u0445\u043e\u0447\u0443 \u0436\u0438\u0442\u044c \u0432 \u043e\u0431\u0449\u0430\u0433\u0435",  # ru: I want to live in the dorm
    "\u0436\u0438\u0442\u044c \u0431\u0435\u0437 \u043a\u043e\u0444\u0435 \u043d\u0435 \u043c\u043e\u0433\u0443",  # ru: can't live without coffee
    "\u04e9\u043b\u0456\u043f \u049b\u0430\u043b\u0434\u044b\u043c",  # kk: I died (laughing)
    "\u0441\u0435\u043d\u0456 \u0436\u0435\u043a \u043a\u04e9\u0440\u0435\u043c\u0456\u043d",  # kk: I hate you
    "this exam is killing me",  # en
    "I'm dead lol",  # en
    "kill this bug in my code",  # en
    "I could die of embarrassment",  # en
    "where is the gym?",  # en
    "I hate you",  # en
    "skillshare for myself",  # en: kms inside a word
    "\u043d\u0435 \u0445\u043e\u0447\u0443 \u0436\u0438\u0442\u044c \u0432 \u043e\u0431\u0449\u0430\u0433\u0435, \u0433\u0434\u0435 \u0441\u043d\u044f\u0442\u044c \u043a\u0432\u0430\u0440\u0442\u0438\u0440\u0443?",  # ru: I don't want to live in the dorm, where to rent?
    "\u043d\u0435 \u0445\u043e\u0447\u0435\u0442\u0441\u044f \u0436\u0438\u0442\u044c \u043d\u0430 \u043e\u043a\u0440\u0430\u0438\u043d\u0435",  # ru: don't feel like living on the outskirts
    "\u043a\u0430\u043a \u0432\u044b\u043f\u0438\u043b\u0438\u0442\u044c\u0441\u044f \u0438\u0437 \u0447\u0430\u0442\u0430 \u0433\u0440\u0443\u043f\u043f\u044b",  # ru slang: how to leave the group chat
    "\u043f\u043e\u0433\u0443\u0431\u0438\u0442\u044c \u0441\u0435\u0431\u044f \u0443\u0447\u0451\u0431\u043e\u0439",  # ru: to ruin oneself with studies
    "\u0410\u043b\u043c\u0430\u0442\u044b\u0434\u0430 \u04e9\u043c\u0456\u0440 \u0441\u04af\u0440\u0433\u0456\u043c \u043a\u0435\u043b\u043c\u0435\u0439\u0434\u0456",  # kk: I don't want to live in Almaty
    "I don't want to live in the dorm",  # en
    "AWS KMS keys for the lab",  # en
    "ran 3 kms today",  # en
    "I hurt myself at the gym, where's the medical office?",  # en
    "I cut myself a break",  # en
    "watching suicide squad tonight",  # en: a film
    "the suicide burn in the physics lab",  # en: a rocket manoeuvre
    "\u043c\u043e\u0436\u0435\u0442 \u043c\u043d\u0435 \u043f\u0440\u043e\u0441\u0442\u043e \u0432\u044b\u043f\u0438\u043b\u0438\u0442\u044c\u0441\u044f",  # ru slang, also "leave a chat": left to the model
    "gonna kms",  # en slang, also "kilometres": left to the model
]


def test_keyword_backstop():
    assert [p for p in CARE if not assistant.distress(p)] == []
    assert [p for p in NOT_CARE if assistant.distress(p)] == []
    assert not assistant.distress(None) and not assistant.distress(5)


def test_care_flag_and_feedback(env, monkeypatch):
    c, cfg = env
    login(c, 1, "ann")  # a Monday Calculus class at 09:00 in room 305
    _board_on(c, cfg)
    con = db.connect(cfg.db_path)
    said: dict = {}
    assistant._HITS.clear()

    async def model(cfg_, http, msgs, **kw):
        assert "care: true only when" in msgs[0]["content"] and NOT_CARE[0] in msgs[0]["content"]  # the rule, with its hyperbole
        return json.dumps(said), "x"
    monkeypatch.setattr(llm, "chat", model)
    ask = lambda q="where is the gym?": c.post("/api/assistant", headers=tma(1), json={"q": q})  # noqa: E731
    count = lambda t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731

    # the model flags care: its words, then the fixed card; no topic, no vote, nothing kept but the week's count
    said.update(text="I'm sorry it's so hard.", actions=[], known=False, topic="feeling bad", care=True)
    r = ask("i feel awful").json()
    assert r == {"text": "I'm sorry it's so hard.", "actions": [], "care": True, "help": texts.HELP_CARD["ru"]}
    assert count("assist_marks") == 0 and con.execute("SELECT SUM(n) FROM assist_care").fetchone()[0] == 1
    assert all("1303" in t and "150" in t and "112" in t for t in texts.HELP_CARD.values())
    # the model misses it, the keywords don't: the card, and no topic kept
    said.update(text="I don't know.", topic="wants to die", care=False)
    assert ask(CARE[0]).json()["care"] and count("assist_marks") == 0

    # an unknown fact keeps its topic; a name (another alphabet, or capitalised past the first word) keeps none
    for t in ("Gym hours \u0410\u0440\u043c\u0430\u043d", "Professor Ivanov office hours"):
        said.update(topic=t, known=False, care="true")  # "true" as a string isn't care
        r = ask().json()
        assert "care" not in r and "mark" not in r
    said.update(topic="Gym <b>opening</b> hours of SITE")
    r = ask().json()
    assert [tuple(x) for x in con.execute("SELECT kind, topic FROM assist_marks")] == [("unknown", "gym b opening b hours of site")]
    said.update(text="Your Calculus is at 09:00 in room 305; the gym is in 1.", known=True, topic="gym and class", care=False)
    a = ask("where is the gym and my class?").json()
    assert count("assist_marks") == 1                                                  # known: nothing kept

    vote = lambda m, v="down": c.post("/api/assistant/vote", headers=tma(1), json={"mark": m, "vote": v})  # noqa: E731
    send = lambda x, **k: c.post("/api/assistant/send", headers=tma(1), json={  # noqa: E731
        "mark": x["mark"], "pair": x["pair"], "q": "where is the gym and my class?", "a": x["text"], **k})
    # a pair can't be sent before its thumbs down, nor with a word changed
    assert send(a).status_code == 409 and send(a, a="made up").status_code == 400 and send(a, q="other").status_code == 400
    # a mark votes once; a forged or another day's mark not at all
    assert vote(a["mark"]).status_code == 204 and vote(a["mark"], "up").status_code == 409
    topic, day, nonce, sig = a["mark"].rsplit(".", 3)
    for bad in (f"arman is sad.{day}.{nonce}.{sig}", f"{topic}.{int(day) - 5}.{nonce}.{sig}", a["mark"], 5):
        assert vote(bad, "meh" if bad == a["mark"] else "up").status_code == 400
    # sent once, without the timetable
    assert send(a).status_code == 204 and send(a).status_code == 409
    assert tuple(con.execute("SELECT q, a FROM assist_sent").fetchone()) == ("where is the gym and my class?",
                                                                         "Your [class] is at [time] in room [room]; the gym is in 1.")
    for t in ("assist_marks", "assist_sent", "assist_care", "assist_votes"):
        assert "user_id" not in [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
    seen = assistant.seen(con)
    assert seen["unknown"] == [{"topic": "gym b opening b hours of site", "n": 1}] and seen["downs"] == 1 and seen["down"][0]["topic"] == "gym and class"
    assert len(seen["sent"]) == 1 and seen["care"][0]["n"] == 2

    # past the day's cap a send is refused out loud (the app says so), not dropped behind a 204
    b = ask().json()
    assert vote(b["mark"]).status_code == 204
    monkeypatch.setattr(assistant, "DAY_SENT", 1)
    assert send(b, q="where is the gym?").json()["error"] == "rate_limited"
    # one client's loop is capped per worker
    for _ in range(15):
        x = ask().json()
        last = vote(x["mark"], "up").status_code
    assert last == 429

    # no model answer: one in distress still gets the card (keywords); anyone else the 503
    async def down(*a, **k):
        raise llm.Busy()
    monkeypatch.setattr(llm, "chat", down)
    assert ask().status_code == 503
    r = ask(CARE[1]).json()
    assert r["care"] and r["text"] == "" and r["help"] == texts.HELP_CARD["ru"]
    # the count can't be looped up (a global cap an hour per worker; the card still shows)
    for _ in range(40):
        assert ask(CARE[1]).json()["care"]
    assert con.execute("SELECT SUM(n) FROM assist_care").fetchone()[0] == 30

    # 30 days on: the feedback is gone, the weekly count stays
    later = logic.now() + 31 * 86400
    monkeypatch.setattr(assistant, "now", lambda: later)
    assistant.sweep(con)
    assert count("assist_marks") + count("assist_sent") + count("assist_votes") == 0
    assert con.execute("SELECT SUM(n) FROM assist_care").fetchone()[0] == 30
    con.close()
