"""Admissions reminders (logic/ako.py, kbtu/akosend.py): the invite opens in one tap by its signature alone, the bot's
link binds one chat and dies with a new link, reminders go once in their windows and only for the current time,
e-mail only when a sender is configured, nothing at all with AKO_REMIND off, and the owner's preview."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import smtplib

from kbtu import akosend, bot_dm, logic, outbox, texts
from kbtu.logic import ako
from helpers import BOT
from test_ako import HEAD, TEAMS, _new, _setup, _slots
from test_core import env, set_clock, tma  # noqa: F401  (env is a fixture)

CHAT = 501


def _sent(c, oid, t0, slot_index=0):
    """A package sent with an interview booked: (its link, its id, the interview's start)."""
    slots = _slots(c, oid, t0)
    tok = _new(c, oid, ready=True)
    h = {"X-Ako": tok}
    assert c.post("/api/ako/a/slot", headers=h, json={"slot": slots[slot_index]}).status_code == 200
    v = c.post("/api/ako/a/submit", headers=h).json()
    assert v["status"] == "sent"
    return tok, v["slot"]["at"]


def _aid(con, tok) -> int:
    return con.execute("SELECT id FROM ako_apps WHERE token = ?", (ako._digest(tok),)).fetchone()[0]


def _start(con, cfg, payload: str, chat: int = CHAT) -> dict | None:
    return bot_dm._welcome(con, cfg, {"chat": {"id": chat, "type": "private"}, "date": logic.now(), "text": f"/start {payload}",
                                      "from": {"id": chat, "language_code": "en"}})


def _payload(c, tok) -> str:
    return c.get("/api/ako/a", headers={"X-Ako": tok}).json()["remind"]["telegram"].split("?start=")[1]


class _Log:
    """A fake channel: records each send and answers with what it is told."""
    def __init__(self, answer=None):
        self.got, self.answer = [], answer

    async def __call__(self, cfg, http, m):
        self.got.append((m["kind"], m["channel"], m["to"]))
        return self.answer


def _tick(cfg, con, monkeypatch, at: int, **senders) -> None:
    set_clock(monkeypatch, lambda: at)
    for name, fn in senders.items():
        monkeypatch.setitem(akosend.SENDERS, name, fn)
    asyncio.run(akosend.tick(cfg, None, con))


def test_the_invite_opens_in_one_tap_by_its_signature(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tok, at = _sent(c, oid, t0)
    aid = _aid(con, tok)
    remind = c.get("/api/ako/a", headers={"X-Ako": tok}).json()["remind"]
    assert remind["telegram"] is None and remind["linked"] is False  # AKO_REMIND off: no bot link
    r = c.get(remind["ics"])  # no header, no session
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar") and "no-store" in r.headers["cache-control"]
    body = r.text.replace("\r\n ", "")
    assert f"UID:ako{aid}@kbtu-app" in body and "SEQUENCE:" in body and TEAMS.replace(",", "\\,") in body
    assert c.get(f"/api/ako/ics/{aid}").status_code == 404
    assert c.get(remind["ics"].replace("?s=", "?s=x")).status_code == 404
    assert c.get(f"/api/ako/ics/{10 ** 30}?s=x").status_code in (404, 422)
    other = _new(c, oid, name="Other")  # another package's signature opens nothing here
    assert c.get(f"/api/ako/ics/{aid}?s={ako._mac('ics', con.execute('SELECT * FROM ako_apps WHERE id = ?', (_aid(con, other),)).fetchone())}").status_code == 404
    # a new link stops the old invite link too
    c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"newLink": True})
    assert c.get(remind["ics"]).status_code == 404
    # no interview, no invite
    assert c.get("/api/ako/a", headers={"X-Ako": other}).json()["remind"]["ics"] is None
    del at


def test_the_bot_link_binds_one_chat(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    tok, _ = _sent(c, oid, t0)
    aid = _aid(con, tok)
    monkeypatch.setattr(ako, "BOT", "")
    forged = f"ako_{aid}_{'A' * 22}"
    assert "inline_keyboard" in _start(con, cfg, forged)["reply_markup"]  # switched off: the plain welcome, nothing bound
    monkeypatch.setattr(ako, "BOT", "KBTUappBot")
    payload = _payload(c, tok)
    assert payload.startswith(f"ako_{aid}_") and len(payload) <= 64
    reply = _start(con, cfg, payload)
    assert reply["text"].startswith("🔔") and "reply_markup" not in reply
    assert con.execute("SELECT tg_chat FROM ako_apps WHERE id = ?", (aid,)).fetchone()[0] == CHAT
    assert c.get("/api/ako/a", headers={"X-Ako": tok}).json()["remind"]["linked"] is True
    assert _start(con, cfg, payload)["text"].startswith("🔔")  # the same chat again: fine
    # a forwarded link takes nothing over; a forged one binds nothing
    assert _start(con, cfg, payload, chat=502)["text"].startswith("⏳")
    assert _start(con, cfg, forged, chat=503)["text"].startswith("⏳")
    assert _start(con, cfg, f"ako_{10 ** 20}_x", chat=503)["text"].startswith("⏳")
    assert con.execute("SELECT tg_chat FROM ako_apps WHERE id = ?", (aid,)).fetchone()[0] == CHAT
    # a new link frees the chat and stops the old payload
    c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"newLink": True})
    assert con.execute("SELECT tg_chat FROM ako_apps WHERE id = ?", (aid,)).fetchone()[0] is None
    assert _start(con, cfg, payload)["text"].startswith("⏳")
    # a decided package binds nothing
    tok2, _ = _sent(c, oid, t0, slot_index=1)
    c.patch(f"/api/orgs/{oid}/ako/apps/{_aid(con, tok2)}", headers=tma(HEAD), json={"status": "declined"})
    assert _start(con, cfg, _payload(c, tok2))["text"].startswith("⏳")


def test_reminders_go_once_in_their_windows(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    monkeypatch.setattr(ako, "BOT", "KBTUappBot")
    tok, at = _sent(c, oid, t0)
    _start(con, cfg, _payload(c, tok))
    tg = _Log()
    _tick(cfg, con, monkeypatch, at - 25 * 3600, telegram=tg)
    assert tg.got == []
    _tick(cfg, con, monkeypatch, at - 23 * 3600, telegram=tg)
    assert tg.got == [("d1", "telegram", CHAT)]
    _tick(cfg, con, monkeypatch, at - 23 * 3600 + 60, telegram=tg)  # the next minute: claimed already
    _tick(cfg, con, monkeypatch, at - 3 * 3600, telegram=tg)        # between the windows
    assert len(tg.got) == 1
    _tick(cfg, con, monkeypatch, at - 1800, telegram=tg)
    _tick(cfg, con, monkeypatch, at - 1800 + 30, telegram=tg)       # the same minute: the round doesn't run
    _tick(cfg, con, monkeypatch, at - 120, telegram=tg)             # too late for an hour's reminder
    assert tg.got == [("d1", "telegram", CHAT), ("h1", "telegram", CHAT)]
    assert con.execute("SELECT COUNT(*) FROM ako_sends WHERE sent_at IS NOT NULL AND error IS NULL").fetchone()[0] == 2
    # the message itself: emoji first, the catalogue's program, the Teams link as its one button
    text, keys = ako.message("ako_h1", "en", "Executive MBA", at, TEAMS)
    assert text.startswith("⏰") and "Executive MBA" in text and keys == [[{"text": "💻 Join in Teams", "url": TEAMS}]]
    assert ako.message("ako_h1", "ru", "EMBA", at, None)[1] is None
    # a day after the interview the chat and the marks go
    set_clock(monkeypatch, lambda: at + 2 * 86400)
    ako.sweep(con)
    assert con.execute("SELECT tg_chat FROM ako_apps WHERE id = ?", (_aid(con, tok),)).fetchone()[0] is None
    assert con.execute("SELECT COUNT(*) FROM ako_sends").fetchone()[0] == 0


def test_no_stale_reminder_for_a_moved_taken_or_decided_time(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    monkeypatch.setattr(ako, "BOT", "KBTUappBot")
    tok, at = _sent(c, oid, t0)
    aid = _aid(con, tok)
    _start(con, cfg, _payload(c, tok))
    # the team takes the time away: nothing goes for it
    assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"slot": None, "reason": "Ill"}).status_code == 200
    tg = _Log()
    _tick(cfg, con, monkeypatch, at - 23 * 3600, telegram=tg)
    assert tg.got == []
    # booked again by the team at another time: that one is reminded
    later = [s for s in c.get(f"/api/orgs/{oid}/ako", headers=tma(HEAD)).json()["slots"] if s["at"] > at][0]
    c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"slot": later["id"]})
    _tick(cfg, con, monkeypatch, later["at"] - 1800, telegram=tg)
    assert tg.got == [("h1", "telegram", CHAT)]
    # decided: nothing more, and the nightly sweep forgets the chat
    c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"status": "accepted"})
    _tick(cfg, con, monkeypatch, later["at"] - 600, telegram=tg)
    assert len(tg.got) == 1
    ako.sweep(con)
    assert con.execute("SELECT tg_chat FROM ako_apps WHERE id = ?", (aid,)).fetchone()[0] is None


def test_a_failed_send_retries_and_a_blocked_chat_is_forgotten(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    monkeypatch.setattr(ako, "BOT", "KBTUappBot")
    tok, at = _sent(c, oid, t0)
    aid = _aid(con, tok)
    _start(con, cfg, _payload(c, tok))
    _tick(cfg, con, monkeypatch, at - 23 * 3600, telegram=_Log("retry"))
    assert con.execute("SELECT COUNT(*) FROM ako_sends").fetchone()[0] == 0  # the claim went: the next round tries again
    _tick(cfg, con, monkeypatch, at - 23 * 3600 + 60, telegram=_Log("blocked"))
    row = con.execute("SELECT sent_at, error FROM ako_sends").fetchone()
    assert row["sent_at"] is None and row["error"] == "blocked"
    assert con.execute("SELECT tg_chat FROM ako_apps WHERE id = ?", (aid,)).fetchone()[0] is None


def test_the_telegram_channel_sends_the_template(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    calls = []

    class R:
        def __init__(self, code):
            self.status_code = code

    async def fake_tg(cfg_, http, method, body, files=None):
        calls.append((method, body))
        return R(calls and len(calls) == 1 and 200 or 403)
    monkeypatch.setattr(akosend, "_tg", fake_tg)
    m = {"kind": "d1", "lang": "kk", "program": "EMBA", "at": t0 + 86400, "teams": TEAMS, "to": CHAT}
    assert asyncio.run(akosend._telegram(cfg, None, m)) is None
    method, body = calls[0]
    assert method == "sendMessage" and body["chat_id"] == CHAT and body["text"].startswith("⏰")
    assert body["reply_markup"]["inline_keyboard"][0][0]["url"] == TEAMS
    assert asyncio.run(akosend._telegram(cfg, None, m)) == "blocked"


class _Smtp:
    sent: list = []
    refuse = False

    def __init__(self, host, port, timeout=None, **kw):
        assert timeout == akosend.SMTP_WAIT

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def has_extn(self, name):
        return False

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if _Smtp.refuse:
            raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no such user")})
        _Smtp.sent.append(msg)


def test_email_only_with_a_sender_and_never_over_its_cap(env, monkeypatch):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    monkeypatch.setattr(smtplib, "SMTP", _Smtp)
    monkeypatch.setattr(_Smtp, "sent", [])
    tok, at = _sent(c, oid, t0)
    c.patch("/api/ako/a", headers={"X-Ako": tok}, json={"email": "erlan@mail.kz"})
    mail = dataclasses.replace(cfg, ako_mail_from="AKO <exed@kbtu.kz>", smtp_host="smtp.example")
    # AKO_REMIND off: nothing, even with a sender
    monkeypatch.setattr(ako, "BOT", "")
    _tick(mail, con, monkeypatch, at - 23 * 3600)
    assert _Smtp.sent == []
    monkeypatch.setattr(ako, "BOT", "KBTUappBot")
    # no sender configured: no e-mail
    assert not akosend.mail_on(cfg)
    _tick(cfg, con, monkeypatch, at - 23 * 3600 + 60)
    assert _Smtp.sent == [] and con.execute("SELECT COUNT(*) FROM ako_sends").fetchone()[0] == 0
    _tick(mail, con, monkeypatch, at - 23 * 3600 + 120)
    kinds = sorted(m["Subject"].split(":")[0] for m in _Smtp.sent)
    assert len(_Smtp.sent) == 2 and all(m["To"] == "erlan@mail.kz" for m in _Smtp.sent), kinds
    invite = [m for m in _Smtp.sent if any(p.get_content_type() == "text/calendar" for p in m.iter_attachments())]
    assert len(invite) == 1  # the invite carries the .ics; the day's reminder doesn't
    text = invite[0].get_body(("plain",)).get_content()
    assert TEAMS in text and "Erlan" not in text  # never the applicant's typed name
    # moving the time sends a new invite, at most INVITES_A_DAY a day
    aid = _aid(con, tok)
    _slots(c, oid, t0, times=("11:00", "11:30", "12:00", "12:30"))
    slots = [s for s in c.get(f"/api/orgs/{oid}/ako", headers=tma(HEAD)).json()["slots"] if s["at"] > at]
    assert len(slots) >= ako.INVITES_A_DAY + 1
    for n, s in enumerate(slots[:ako.INVITES_A_DAY + 1], 1):
        assert c.patch(f"/api/orgs/{oid}/ako/apps/{aid}", headers=tma(HEAD), json={"slot": s["id"]}).status_code == 200
        _tick(mail, con, monkeypatch, at - 23 * 3600 + 120 + 60 * n)
    assert con.execute("SELECT COUNT(*) FROM ako_sends WHERE kind = 'booked'").fetchone()[0] == ako.INVITES_A_DAY
    # a refused address: kept as the error's class, never the address, and not tried again
    monkeypatch.setattr(_Smtp, "refuse", True)
    c.patch("/api/ako/a", headers={"X-Ako": tok}, json={"email": "nobody@mail.kz"})
    con.execute("DELETE FROM ako_sends")
    _tick(mail, con, monkeypatch, at - 23 * 3600 + 3600)
    errors = {r[0] for r in con.execute("SELECT error FROM ako_sends WHERE channel = 'email'")}
    assert errors == {"SMTPRecipientsRefused"}


def test_the_owner_previews_the_texts(env, monkeypatch, capsys):
    c, cfg, con, oid, t0 = _setup(env, monkeypatch)
    for k, v in (("BOT_TOKEN", BOT), ("TOKEN_KEY", "A" * 43 + "="), ("DB_PATH", cfg.db_path)):
        monkeypatch.setenv(k, v)
    from kbtu import admin
    admin.main(["ako-preview", str(HEAD)])
    assert capsys.readouterr().out.strip() == "queued 3"
    got = con.execute("""SELECT b.*, u.lang FROM bot_outbox b JOIN users u ON u.id = b.user_id WHERE b.kind LIKE 'ako_%' ORDER BY b.kind""").fetchall()
    assert [g["kind"] for g in got] == ["ako_d1", "ako_h1", "ako_linked"]
    for lang in ("ru", "kk", "en"):
        for g in got:
            text, button, keys = outbox._render(con, {**dict(g), "lang": lang})
            assert text[0] in "⏰🔔" and button is None
            assert keys == "" if g["kind"] == "ako_linked" else keys[0][0]["url"].startswith("https://teams.microsoft.com/")
    # every ako template opens with an emoji and has the same fields in each language
    for kind in ("ako_linked", "ako_gone", "ako_d1", "ako_h1"):
        assert len({json.dumps(sorted(set(re.findall(r"{(\w+)}", texts.BOT[lang][kind][0])))) for lang in ("ru", "kk", "en")}) == 1
        assert all(texts.BOT[lang][kind][0][0] in "🔔⏳⏰" for lang in ("ru", "kk", "en"))
