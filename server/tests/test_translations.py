"""Translations: bot texts in every language, translated titles and role names."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time

import pytest

from kbtu import ai, db, logic, outbox, texts
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def test_bot_texts_match_across_languages():
    """Every bot message and share card uses the same fields in ru, kk and en: a field only one language asks for would
    fail only for the people reading it."""
    import string
    fields = lambda tpl: {f for _, f, _, _ in string.Formatter().parse(tpl or "") if f}
    for table in (texts.BOT, texts.SHARE_REFER, texts.SHARE_JOIN, texts.SHARE_PRES, texts.SHARE_AWARD):
        for key in (table["ru"] if table is texts.BOT else [None]):
            ru = table["ru"][key] if key else table["ru"]
            for lang in ("kk", "en"):
                other = table[lang][key] if key else table[lang]
                assert [fields(x) for x in ru if isinstance(x, str)] == [fields(x) for x in other if isinstance(x, str)], (key, lang)


def test_bot_texts_open_with_an_emoji():
    """The owner's hard rule: every bot message starts with an emoji (a bare paragraph gets skipped)."""
    import unicodedata
    for lang, table in texts.BOT.items():
        for key, v in table.items():
            text = (v[0] if isinstance(v, tuple) else v).lstrip()
            if isinstance(text, str) and text and not text.startswith("{"):
                assert unicodedata.category(text[0]) == "So" or text[0] in "ℹ", (lang, key, text[:30])


def test_translations(env):
    """PLAN 9 (ai.py): the source language from the letters; the model's answer parsed or refused; only public published
    events and active clubs are sent; an edit of the text (not of the time) translates again; a translation never
    overwrites an edit made meanwhile; 3 failures leave it; cards carry titles, the club's description only its page."""
    import httpx
    from kbtu import ai
    assert (ai.lang_of("\u049a\u043e\u0448 \u043a\u0435\u043b\u0434\u0456\u04a3"), ai.lang_of("\u041f\u0440\u0438\u0432\u0435\u0442, \u043c\u0438\u0440"), ai.lang_of("KBTU Open 2026")) == ("kk", "ru", "en")
    L = {"title": 80, "description": 2000}
    good = 'Sure!\n```json\n{"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456"}, "en": {"title": "Hack night"}}\n```'
    assert ai.parse(good, {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430"}, "ru", L) == {"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456"}, "en": {"title": "Hack night"}}
    for bad in (None, "", "no json here", '{"kk": {"title": "x"}}', '{"kk": {"title": "x"}, "en": {"title": 5}}', '{"kk": {}, "en": {}}'):
        with pytest.raises(ai.Failed):
            ai.parse(bad, {"title": "\u041d\u043e\u0447\u044c"}, "ru", L)
    assert ai.parse('{"kk": {"title": "' + "\u0430" * 300 + '"}, "en": {"title": "b"}}', {"title": "\u041d\u043e\u0447\u044c"}, "ru", L)["kk"]["title"] == "\u0430" * 80

    # the AI chain (llm.py): the next link when one is limited, busy or unusable; a limited one rests, an unusable one doesn't
    import dataclasses
    from kbtu import llm
    chained = dataclasses.replace(env[1], cf_account_id="acc", cf_ai_token="cf", munito_keys=("m1", "m2"), groq_key="gq",
                                  ai_chain="cf:model-a,munito:model-b,groq:model-c")
    assert [x.name for x in llm.links(chained)] == ["cf:model-a", "munito:model-b", "munito2:model-b", "groq:model-c"]
    assert not llm.available(env[1])                                                   # no keys: no chain, the translator stays off
    good_answer = {"choices": [{"finish_reason": "stop", "message": {"content": '{"kk": {"title": "\u0422"}, "en": {"title": "N"}}'}}]}
    def call(answers: dict):
        seen = []
        def handler(r):
            key = r.headers["authorization"].split()[1]
            seen.append(key)
            return answers.get(key) or httpx.Response(200, json=good_answer)
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                return await ai.translate(chained, http, {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430", "description": ""}, L)
        return asyncio.run(go()), seen
    llm._rest.clear()
    import itertools
    llm._turn = itertools.count()
    assert [call({})[1] for _ in range(3)] == [["m1"], ["m2"], ["m1"]]                   # the keys take turns: each call starts from the next
    llm._turn = itertools.repeat(0)                                                     # below: the first key first, to read the order
    # translations ask Munito, Groq, Cloudflare in that order (ai.TRANSLATE_PROVIDERS), whatever AI_CHAIN's order
    assert call({}) == (("ru", {"kk": {"title": "\u0422"}, "en": {"title": "N"}}), ["m1"])     # the empty description isn't sent
    assert call({"m1": httpx.Response(429, headers={"retry-after": "120"})})[1] == ["m1", "m2"]
    assert call({})[1] == ["m2"]                                                         # m1 rests its two minutes
    assert call({"m2": httpx.Response(503)})[1] == ["m2", "gq"]                          # then Groq
    llm._rest.clear()
    assert call({"m1": httpx.Response(200, json={"choices": [{"message": {"content": "no json here"}}]})})[1] == ["m1", "m2"]
    assert call({})[1] == ["m1"]                                                         # a bad answer doesn't rest the link
    llm._rest.clear()
    assert call({k: httpx.Response(503) for k in ("m1", "m2", "gq")})[1] == ["m1", "m2", "gq", "cf"]  # Cloudflare last
    llm._rest.clear()
    with pytest.raises(ai.Busy):
        call({"m1": httpx.Response(503), "m2": httpx.Response(503), "gq": httpx.Response(503),
              "cf": httpx.Response(400, json={"errors": [{"code": 4006}]})})
    assert llm._rest["cf:model-a"] > time.time() + 3600                                  # Cloudflare's day spent: rests for hours
    llm._rest.clear()
    busy = {k: httpx.Response(503) for k in ("cf", "m1", "m2", "gq")}
    with pytest.raises(ai.Busy):
        call(busy)
    assert call({})[1] == ["m1"]                                                         # all resting: the soonest is asked anyway
    llm._rest.clear()
    junk = {k: httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": None}}]}) for k in ("cf", "m1", "m2", "gq")}
    with pytest.raises(ai.Failed):
        call(junk)
    llm._rest.clear()

    c, cfg = env
    pres = login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at, description, official) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0, '', 1)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ?, 'president', 0)", (pres["id"],))
    start = (int(time.time()) // 86400 + 1) * 86400 + 7 * 3600  # noon in Almaty: the range stays within one day
    body = {"seats": None, "title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430", "description": "\u041a\u043e\u0434\u0438\u043c \u0434\u043e \u0443\u0442\u0440\u0430", "place": "305", "startsAt": start, "endsAt": start + 7200,
            "emoji": "laptop_3d", "color": "#3B6BFF"}
    ev = c.post("/api/orgs/1/events", headers=tma(20), json=body).json()
    assert logic.ai_next(con) is None                                     # a draft stays home; a club with no description too
    c.post(f"/api/events/{ev['id']}/publish", headers=tma(20))
    kind, rid, was = logic.ai_next(con)
    assert (kind, rid, was) == ("event", ev["id"], {"title": "\u041d\u043e\u0447\u044c \u0445\u0430\u043a\u0430\u0442\u043e\u043d\u0430", "description": "\u041a\u043e\u0434\u0438\u043c \u0434\u043e \u0443\u0442\u0440\u0430"})
    tr = {"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456", "description": "\u0422\u0430\u04a3\u0493\u0430 \u0434\u0435\u0439\u0456\u043d"}, "en": {"title": "Hack night", "description": "Code till dawn"}}
    logic.ai_save(con, kind, rid, was, "ru", tr)
    assert logic.ai_next(con) is None
    full = c.get(f"/api/events/{rid}", headers=tma(20)).json()
    assert full["i18n"]["en"] == {"title": "Hack night", "description": "Code till dawn"}
    assert logic.core.cards(con, logic.Viewer(pres["id"], "student", True), [logic.one(con, "SELECT * FROM events WHERE id = ?", rid)])[0]["i18n"] == \
        {"kk": {"title": "\u0425\u0430\u043a\u0430\u0442\u043e\u043d \u0442\u04af\u043d\u0456"}, "en": {"title": "Hack night"}}
    post = logic.channel_due(con, "bot")[0][1]
    assert "Hack night" not in post and "\u0425\u0430\u043a\u0430\u0442\u043e\u043d" not in post  # no translations: the title as written
    d = time.gmtime(start + 5 * 3600)
    assert "\U0001f5d3 %02d.%02d \u00b7 %02d:%02d\u2013" % (d.tm_mday, d.tm_mon, d.tm_hour, d.tm_min) in post and "\n\U0001f4cd 305\n\U0001f39f Free\n\n<a href=" in post and "KBTU App \u2192</a>" in post and "<b>\u041d" in post

    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "place": "306"})   # not the text: the translation stays
    assert logic.ai_next(con) is None
    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "title": "\u041d\u043e\u0447\u044c \u043a\u043e\u0434\u0430"})
    kind, rid, was = logic.ai_next(con)
    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "title": "\u041d\u043e\u0447\u044c \u043a\u043e\u0434\u0430 2"})  # edited while the model thought
    logic.ai_save(con, kind, rid, was, "ru", {"kk": {"title": "x", "description": "x"}, "en": {"title": "x", "description": "x"}})
    assert one_val(con, "SELECT i18n FROM events WHERE id = ?", rid) is None and logic.ai_next(con)[2]["title"] == "\u041d\u043e\u0447\u044c \u043a\u043e\u0434\u0430 2"
    for _ in range(3):
        logic.ai_failed(con, "event", rid, "bad")
    assert logic.ai_next(con) is None and logic.queues.ai_state(con)["error"].endswith("event %d: bad" % rid)

    c.patch(f"/api/events/{rid}", headers=tma(20), json={**body, "title": "\u0421\u0431\u043e\u0440 \u043a\u043e\u043c\u0430\u043d\u0434\u044b", "visibility": "members"})
    assert logic.ai_next(con) is None                                     # a team-only event never goes out

    # the club: its description, kept apart from the name; cards don't carry it
    c.patch("/api/orgs/1", headers=tma(20), json={"description": "\u041c\u044b \u0434\u0435\u043b\u0430\u0435\u043c \u0432\u0435\u0449\u0438."})
    con.execute("UPDATE orgs SET i18n = ? WHERE id = 1", (json.dumps({"kk": {"name": "IT \u043a\u043b\u0443\u0431\u044b"}}),))
    kind, oid, was = logic.ai_next(con)
    assert (kind, oid, was) == ("org", 1, {"description": "\u041c\u044b \u0434\u0435\u043b\u0430\u0435\u043c \u0432\u0435\u0449\u0438."})
    logic.ai_save(con, kind, oid, was, "ru", {"kk": {"description": "\u0411\u0456\u0437 \u0436\u0430\u0441\u0430\u0439\u043c\u044b\u0437."}, "en": {"description": "We build things."}})
    assert json.loads(one_val(con, "SELECT i18n FROM orgs WHERE id = 1")) == {"kk": {"name": "IT \u043a\u043b\u0443\u0431\u044b", "description": "\u0411\u0456\u0437 \u0436\u0430\u0441\u0430\u0439\u043c\u044b\u0437."},
                                                                             "en": {"description": "We build things."}}
    assert "description" not in logic.core.org_ref(con, logic.one(con, "SELECT * FROM orgs WHERE id = 1"))["i18n"]["kk"]
    assert logic.queues.ai_state(con)["today"] == 2
    c.patch("/api/orgs/1", headers=tma(20), json={"description": "\u041d\u043e\u0432\u043e\u0435."})
    assert json.loads(one_val(con, "SELECT i18n FROM orgs WHERE id = 1")) == {"kk": {"name": "IT \u043a\u043b\u0443\u0431\u044b"}} and logic.ai_next(con)[0] == "org"
    con.close()
    llm._turn = itertools.count()


def test_role_titles(env):
    """Owner, Nov 6: a club role's title is typed once in any language; the translator (ai_next/ai_save) fills the other
    two, never a correction made by hand; the same text keeps them, a new one asks again; a Russian title another role
    has stays the typed one. Roles from before: a batch a night (stats_day) joins the queue, their own kk/en kept."""
    c, cfg = env
    login(c, 20, "pres")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) SELECT 1, id, 'president', 0 FROM users WHERE tg_id = 20")
    roles = lambda: {r["id"]: r for r in c.get("/api/orgs/1/team", headers=tma(20)).json()["roles"]}  # noqa: E731
    sec = "\u0421\u0435\u043a\u0440\u0435\u0442\u0430\u0440\u044c"
    body = {"name": sec, "color": "#FF4FA3", "rights": ["door"]}
    rid = next(iter(c.post("/api/orgs/1/roles", headers=tma(20), json=body).json()["roles"]))["id"]
    r = roles()[rid]
    assert (r["name"], r["nameKk"], r["nameEn"], r["src"], r["hand"], r["translating"]) == (sec, None, None, "ru", [], True)
    assert logic.ai_next(con) == ("role", rid, {"title": sec})
    tr = lambda k, e: {"kk": {"title": k}, "en": {"title": e}}  # noqa: E731
    logic.ai_save(con, "role", rid, {"title": sec}, "ru", tr("\u0425\u0430\u0442\u0448\u044b", "Secretary"))
    assert logic.ai_next(con) is None and (roles()[rid]["nameKk"], roles()[rid]["nameEn"], roles()[rid]["translating"]) == ("\u0425\u0430\u0442\u0448\u044b", "Secretary", False)
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(20), json={**body, "color": "#2FBF71"})   # the same text: kept
    assert logic.ai_next(con) is None and roles()[rid]["nameEn"] == "Secretary"
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(20), json={**body, "tr": {"en": "Club secretary"}})  # a correction by hand
    c.patch(f"/api/orgs/1/roles/{rid}", headers=tma(20), json={**body, "name": sec + " 2", "tr": {"en": "Club secretary"}})  # retyped
    assert logic.ai_next(con) == ("role", rid, {"title": sec + " 2"})
    logic.ai_save(con, "role", rid, {"title": sec}, "ru", tr("x", "x"))                      # for the old text: dropped
    logic.ai_save(con, "role", rid, {"title": sec + " 2"}, "ru", tr("\u0425\u0430\u0442\u0448\u044b 2", "Secretary 2"))
    r = roles()[rid]
    assert (r["name"], r["nameKk"], r["nameEn"], r["hand"]) == (sec + " 2", "\u0425\u0430\u0442\u0448\u044b 2", "Club secretary", ["en"])

    # typed in English: the Russian slot (`name`) holds it till the AI writes Russian; one another role has: kept as typed
    eid = c.post("/api/orgs/1/roles", headers=tma(20), json={**body, "name": "Treasurer"}).json()["roles"][-1]["id"]
    assert (roles()[eid]["name"], roles()[eid]["nameEn"], roles()[eid]["src"]) == ("Treasurer", "Treasurer", "en")
    assert logic.ai_next(con) == ("role", eid, {"title": "Treasurer"})
    logic.ai_save(con, "role", eid, {"title": "Treasurer"}, "en", {"kk": {"title": "\u049a\u0430\u0437\u044b\u043d\u0430\u0448\u044b"}, "ru": {"title": sec + " 2"}})
    assert (roles()[eid]["name"], roles()[eid]["nameKk"], roles()[eid]["translating"]) == ("Treasurer", "\u049a\u0430\u0437\u044b\u043d\u0430\u0448\u044b", False)
    for _ in range(3):
        c.patch(f"/api/orgs/1/roles/{eid}", headers=tma(20), json={**body, "name": "Cashier"})
        logic.ai_failed(con, "role", eid, "bad")
    assert logic.ai_next(con) is None and not roles()[eid]["translating"]                   # 3 failures: left as typed

    # roles from before (src NULL): 50 a night; what they had was typed by hand and stays; official ones never go
    for i in range(52):
        con.execute("INSERT INTO org_roles (org_id, name, name_kk, color, level, created_at) VALUES (1, ?, ?, '#FF4FA3', 'member', 0)",
                    (f"{sec} {i + 10}", "\u0425" if i == 0 else None))
    con.execute("INSERT INTO org_roles (org_id, name, color, level, fixed, created_at) VALUES (1, 'Head', '#3B6BFF', 'head', 1, 0)")
    old = con.execute("SELECT MIN(id) FROM org_roles WHERE src IS NULL").fetchone()[0]
    logic.teams.roles_backfill(con)
    assert con.execute("SELECT COUNT(*) FROM org_roles WHERE src IS NULL").fetchone()[0] == 3  # 2 next night, the official one never
    assert logic.ai_next(con)[0] == "role"
    o = con.execute("SELECT src, hand, ai_wait, name_kk FROM org_roles WHERE id = ?", (old,)).fetchone()
    assert tuple(o) == ("ru", "kk", 1, "\u0425")
    logic.ai_save(con, "role", old, {"title": f"{sec} 10"}, "ru", tr("y", "Secretary 10"))
    assert tuple(con.execute("SELECT name_kk, name_en FROM org_roles WHERE id = ?", (old,)).fetchone()) == ("\u0425", "Secretary 10")

    # review: a Kazakh name with another Kazakh title (kk "SMM") stays the Russian slot's, its letters aside; the AI's
    # answer for the "wrong" language still ends the wait, never holding the queue
    con.execute("DELETE FROM org_roles WHERE src IS NULL OR ai_wait = 1")
    kz = "\u0416\u0435\u0442\u0435\u043a\u0448\u0456"
    odd = con.execute("INSERT INTO org_roles (org_id, name, name_kk, color, level, created_at) VALUES (1, ?, 'SMM', '#FF4FA3', 'member', 0)", (kz,)).lastrowid
    logic.teams.roles_backfill(con)
    assert tuple(con.execute("SELECT src, hand, ai_wait FROM org_roles WHERE id = ?", (odd,)).fetchone()) == ("ru", "kk", 1)
    assert logic.ai_next(con) == ("role", odd, {"title": kz})
    logic.ai_save(con, "role", odd, {"title": kz}, "kk", {"ru": {"title": "x"}, "en": {"title": "Lead"}})
    assert tuple(con.execute("SELECT name, name_kk, name_en, ai_wait FROM org_roles WHERE id = ?", (odd,)).fetchone()) == (kz, "SMM", "Lead", 0)
    assert logic.ai_next(con) is None
    # an answer that never matches the row counts a try: three and it's left, the queue moves on
    c.patch(f"/api/orgs/1/roles/{odd}", headers=tma(20), json={**body, "name": "Mentor"})
    for _ in range(3):
        assert logic.ai_next(con)[1] == odd
        logic.ai_save(con, "role", odd, {"title": "not it"}, "en", tr("x", "x"))
    assert logic.ai_next(con) is None
    # the nightly batch never overwrites a save that normalized the row meanwhile
    late = con.execute("INSERT INTO org_roles (org_id, name, color, level, created_at) VALUES (1, 'Late', '#FF4FA3', 'member', 0)").lastrowid
    stale = logic.one(con, "SELECT * FROM org_roles WHERE id = ?", late)
    con.execute("UPDATE org_roles SET src = 'en', hand = 'kk', name_kk = 'K' WHERE id = ?", (late,))
    logic.teams.normalize_role(con, stale)
    assert tuple(con.execute("SELECT src, hand, name_kk FROM org_roles WHERE id = ?", (late,)).fetchone()) == ("en", "kk", "K")
    con.close()


def one_val(con, sql: str, *args):
    return logic.one(con, sql, *args)[0]


def test_bot_and_calendar_titles_translated(env):
    """PLAN 9's deferred part: the bot's messages and my calendar feed show an event's title in my language when it has
    a translation (made up here), else as typed."""
    c, cfg = env
    pres, ali = login(c, 92, "pres"), login(c, 93, "ali")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'it', 'club', 'IT Club', 'IT', 'laptop_3d', 0)")
    ru = "\u041d\u043e\u0447\u044c \u043d\u0430\u0441\u0442\u043e\u043b\u043e\u043a"  # "Board games night" in Russian
    i18n = json.dumps({"en": {"title": "Board games night", "description": ""}, "kk": {"title": "Kk title", "description": ""}})
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, emoji, color, created_by, created_at, updated_at, i18n, lang)
        VALUES (1, 1, 'published', ?, '305', ?, 'laptop_3d', '#3B6BFF', ?, 0, 0, ?, 'ru')""", (ru, int(time.time()) + 86400, pres["id"], i18n))
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'TABCDEF', 0, 0)", (ali["id"],))
    logic.notify(con, ali["id"], "rate", "rate:1")
    ping = lambda lang: con.execute("SELECT b.*, ? AS lang FROM bot_outbox b WHERE kind = 'rate'", (lang,)).fetchone()  # noqa: E731
    assert "Board games night" in outbox._render(con, ping("en"))[0] and ru in outbox._render(con, ping("ru"))[0]
    con.execute("UPDATE users SET lang = 'en' WHERE id = ?", (ali["id"],))
    token = c.post("/api/me/calendar", headers=tma(93, "Ali")).json()["page"].rsplit("/", 1)[1]
    assert "SUMMARY:Board games night" in c.get(f"/cal/{token}.ics").text
    con.execute("UPDATE users SET lang = 'ru' WHERE id = ?", (ali["id"],))
    assert ru in c.get(f"/cal/{token}.ics").text                                               # the source language as typed


def test_bot_cards_for_helpers_and_invites(env):
    """The bot's cards about an event for one person (_render): a volunteer's yes/no, an invitation to a leaders'
    meeting; quiet once the decision changed or they signed up."""
    c, cfg = env
    pres, vol = login(c, 61, "pres"), login(c, 62, "vol")
    con = db.connect(cfg.db_path)
    con.execute("INSERT INTO orgs (id, slug, kind, name, short, emoji, created_at) VALUES (1, 'mic', 'club', 'Open Mic', 'OM', 'laptop_3d', 0)")
    start = logic.now() + 3 * 86400
    con.execute("""INSERT INTO events (id, org_id, status, title, place, starts_at, ends_at, emoji, color, created_by, created_at, updated_at)
        VALUES (1, 1, 'published', 'Jam', '305', ?, ?, 'laptop_3d', '#3B6BFF', ?, 0, 0)""", (start, start + 3600, pres["id"]))
    con.execute("INSERT INTO volunteers (event_id, user_id, status, created_at) VALUES (1, ?, 'yes', 0)", (vol["id"],))
    card = lambda kind, ref: outbox._render(con, {"kind": kind, "ref": ref, "lang": "ru", "user_id": vol["id"], "payload": None})  # noqa: E731
    fields = dict(org="Open Mic", title="Jam", when=texts.when(start, "ru"), place=texts.place_or_tba("305", "ru"))
    assert card("volunteer_yes", "vo:1:0") == (*texts.bot_message("ru", "volunteer_yes", **fields), "ev_1")
    assert card("volunteer_no", "vo:1:0") is None                                      # the decision says yes
    for kind in ("leaders_invite", "meeting_invite"):
        assert card(kind, "li:1") == (*texts.bot_message("ru", kind, **fields), "ev_1")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', 'T62ABC', 0, 0)", (vol["id"],))
    assert card("leaders_invite", "li:1") is None                                      # answered by signing up
