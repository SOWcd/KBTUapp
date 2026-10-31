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
    "\u043c\u043e\u0436\u0435\u0442 \u043c\u043d\u0435 \u043f\u0440\u043e\u0441\u0442\u043e \u0432\u044b\u043f\u0438\u043b\u0438\u0442\u044c\u0441\u044f",  # ru slang: just off myself
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
    "gonna kms",  # en slang
    "I want to end my life",  # en
    "dont want to be alive",  # en
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
]


def test_keyword_backstop():
    assert [p for p in CARE if not assistant.distress(p)] == []
    assert [p for p in NOT_CARE if assistant.distress(p)] == []
    assert not assistant.distress(None) and not assistant.distress(5)


def test_care_flag_and_feedback(env, monkeypatch):
    c, cfg = env
    login(c, 1, "ann")
    _board_on(c, cfg)
    con = db.connect(cfg.db_path)
    said: dict = {}

    async def model(cfg_, http, msgs, **kw):
        assert "care: true only when" in msgs[0]["content"] and NOT_CARE[0] in msgs[0]["content"]  # the rule, with its hyperbole
        return json.dumps(said), "x"
    monkeypatch.setattr(llm, "chat", model)
    ask = lambda q="where is the gym?": c.post("/api/assistant", headers=tma(1), json={"q": q})  # noqa: E731

    # the model flags care: its words, then the fixed card; no topic, no vote, nothing kept but the week's count
    said.update(text="I'm sorry it's so hard.", actions=[], known=False, topic="feeling bad", care=True)
    r = ask("i feel awful").json()
    assert r == {"text": "I'm sorry it's so hard.", "actions": [], "care": True, "help": texts.HELP_CARD["ru"]}
    assert con.execute("SELECT COUNT(*) FROM assist_marks").fetchone()[0] == 0
    assert con.execute("SELECT SUM(n) FROM assist_care").fetchone()[0] == 1
    assert all("1303" in t and "150" in t and "112" in t for t in texts.HELP_CARD.values())

    # care false (or "true" as a string): a normal answer; an unknown fact keeps its topic, cleaned; the topic comes signed
    said.update(text="I don't know, ask Student services.", known=False, topic="Gym <b>opening</b> hours \u0410\u0440\u043c\u0430\u043d", care="true")
    r = ask().json()
    assert "care" not in r and r["mark"].startswith("gym b opening b hours.")
    assert [tuple(x) for x in con.execute("SELECT kind, topic FROM assist_marks")] == [("unknown", "gym b opening b hours")]
    said.update(known=True, topic="library room", care=False)
    mark = ask().json()["mark"]
    assert con.execute("SELECT COUNT(*) FROM assist_marks").fetchone()[0] == 1          # known: nothing kept

    # a vote: only on a topic we signed; a pair sent on the student's tap; no user id in any of the tables
    assert c.post("/api/assistant/vote", headers=tma(1), json={"mark": mark, "vote": "down"}).status_code == 204
    for bad in ({"mark": "arman is sad." + mark.split(".")[1], "vote": "down"}, {"mark": mark, "vote": "meh"}, {"mark": 5, "vote": "up"}):
        assert c.post("/api/assistant/vote", headers=tma(1), json=bad).status_code == 400
    assert c.post("/api/assistant/send", headers=tma(1), json={"q": "where is the gym?", "a": "I don't know."}).status_code == 204
    assert c.post("/api/assistant/send", headers=tma(1), json={"q": "x", "a": "y"}).status_code == 400
    for t in ("assist_marks", "assist_sent", "assist_care"):
        assert "user_id" not in [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
    seen = assistant.seen(con)
    assert seen["unknown"] == [{"topic": "gym b opening b hours", "n": 1}] and seen["downs"] == 1 and seen["down"][0]["topic"] == "library room"
    assert [(s["q"], s["a"]) for s in seen["sent"]] == [("where is the gym?", "I don't know.")] and seen["care"][0]["n"] == 1

    # no model answer: one in distress still gets the card (keywords); anyone else the 503
    async def down(*a, **k):
        raise llm.Busy()
    monkeypatch.setattr(llm, "chat", down)
    assert ask().status_code == 503
    r = ask(CARE[0]).json()
    assert r["care"] and r["text"] == "" and r["help"] == texts.HELP_CARD["ru"]

    # 30 days on: the feedback is gone, the weekly count stays
    later = logic.now() + 31 * 86400
    monkeypatch.setattr(assistant, "now", lambda: later)
    assistant.sweep(con)
    assert con.execute("SELECT (SELECT COUNT(*) FROM assist_marks) + (SELECT COUNT(*) FROM assist_sent)").fetchone()[0] == 0
    assert con.execute("SELECT SUM(n) FROM assist_care").fetchone()[0] == 2
    con.close()
