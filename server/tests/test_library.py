"""Library seats (logic/library.py, LIBRARY): scan a table, sit, "nobody here" with one answer, the false-report
strikes, the big screen, the admin's rooms and stickers, the account's deletion."""
from __future__ import annotations

import base64
import dataclasses
import io

from kbtu import bot, db, logic, outbox
from helpers import delete_now, env, login, set_clock, tma  # noqa: F401  (env: the fixture)


def _on(c, cfg, monkeypatch, mode: str = "all") -> None:
    c.app.state.cfg = dataclasses.replace(cfg, library=mode)
    monkeypatch.setattr(logic.library, "MODE", mode)


def _setup(c, con, boss_id: int) -> dict:
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (boss_id,))
    rid = c.post("/api/admin/library/rooms", headers=tma(1), json={"name": "Library, floor 2"}).json()[0]["id"]
    return c.post(f"/api/admin/library/rooms/{rid}/tables", headers=tma(1), json={"seats": 4, "n": 3}).json()[0]


def test_library_off_and_staff(env, monkeypatch):
    c, cfg = env
    login(c, 2, "ann")
    mod = login(c, 5, "mod")
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod["id"],))
    assert c.get("/api/library", headers=tma(2)).status_code == 404                                   # off by default
    assert "library" not in c.get("/api/me", headers=tma(2)).json()
    assert c.get("/api/library/screen/whatever-key-x").status_code == 404
    _on(c, cfg, monkeypatch, "staff")
    assert c.get("/api/library", headers=tma(2)).status_code == 404                                   # a student: not yet
    assert c.get("/api/me", headers=tma(5)).json()["library"] == {"consent": False}
    assert c.get("/api/library", headers=tma(5)).json()["rooms"] == []
    assert c.post("/api/admin/library/rooms", headers=tma(5), json={"name": "x"}).status_code == 403  # the admin's alone
    con.close()


def test_library_seats(env, monkeypatch):
    c, cfg = env
    boss, ann, bob, cat = login(c, 1, "boss"), login(c, 2, "ann"), login(c, 3, "bob"), login(c, 4, "cat")
    con = db.connect(cfg.db_path)
    _on(c, cfg, monkeypatch)
    room = _setup(c, con, boss["id"])
    tabs = room["tables"]
    assert [t["label"] for t in tabs] == ["1", "2", "3"] and tabs[0]["seats"] == ["free"] * 4 and room["free"] == 12
    code = tabs[0]["code"]
    assert code.startswith("KBTU-LIB-") and len({t["code"] for t in tabs}) == 3
    scr = c.get(f"/api/library/screen/{room['screen']}").json()                                       # the wall: no sign-in
    assert (scr["free"], scr["total"], scr["tables"][0]) == (12, 12, {"label": "1", "seats": ["free"] * 4})
    assert "code" not in str(scr)

    # a scan: a link or someone else's QR is no table; the code in any case is
    assert c.post("/api/library/table", headers=tma(2), json={"code": "https://t.me/KBTUappBot"}).status_code == 404
    assert c.post("/api/library/table", headers=tma(2), json={"code": code.lower()}).json()["seats"] == ["free"] * 4
    # a seat asks the feature's own consent first, then it's mine for 3 hours
    t0 = logic.now()
    set_clock(monkeypatch, lambda: t0)
    assert c.post("/api/library/sit", headers=tma(2), json={"code": code, "seat": 1}).status_code == 403
    r = c.post("/api/library/sit", headers=tma(2), json={"code": code, "seat": 1, "consent": "lib1"}).json()
    assert r["table"]["seats"] == ["mine", "free", "free", "free"] and r["state"]["mine"]["until"] == t0 + logic.library.HOLD
    assert c.get("/api/me", headers=tma(2)).json()["library"] == {"consent": True}
    assert c.post("/api/library/sit", headers=tma(3), json={"code": code, "seat": 1, "consent": "lib1"}).status_code == 409
    assert c.post("/api/library/sit", headers=tma(3), json={"code": code, "seat": 5, "consent": "lib1"}).status_code == 400
    view = c.post("/api/library/table", headers=tma(3), json={"code": code}).json()
    assert view["seats"][0] == "taken" and "ann" not in str(view).lower()                            # never who
    soon = con.execute("SELECT * FROM bot_outbox WHERE kind = 'lib_soon'").fetchone()
    assert soon["send_after"] == t0 + logic.library.HOLD - logic.library.SOON
    assert outbox._render(con, {**dict(soon), "lang": "ru"})[2] == "lib"

    # "nobody here": the holder gets the template, the seat shows as being checked
    r = c.post("/api/library/report", headers=tma(3), json={"code": code, "seat": 1, "consent": "lib1"}).json()  # a refused tap kept no consent
    assert r["table"]["seats"][0] == "asked" and r["state"]["report"]["state"] == "wait"
    rid = r["state"]["report"]["id"]
    assert c.post("/api/library/table", headers=tma(4), json={"code": code}).json()["seats"][0] == "reported"
    m = con.execute("SELECT * FROM bot_outbox WHERE kind = 'lib_report'").fetchone()
    text, button, start = outbox._render(con, {**dict(m), "lang": "en"})
    assert m["user_id"] == ann["id"] and start == "lib" and "<b>1</b>" in text and "Ann" not in text and text.startswith("🪑")
    assert c.get("/api/library", headers=tma(2)).json()["mine"]["asked"] == t0 + logic.library.CONFIRM
    assert c.post("/api/library/report", headers=tma(4), json={"code": code, "seat": 1, "consent": "lib1"}).status_code == 409  # once
    assert c.post("/api/library/report", headers=tma(2), json={"code": code, "seat": 1}).status_code == 400  # my own seat

    # "I'm here" from the app answers it; the reporter may then say "still not here", once, with this table's code
    assert c.post("/api/library/here", headers=tma(2)).json()["mine"]["asked"] is None
    assert outbox._render(con, {**dict(m), "lang": "en"}) is None
    assert c.get("/api/library", headers=tma(3)).json()["report"]["state"] == "here"
    assert c.post("/api/library/still", headers=tma(3), json={"code": tabs[1]["code"], "report": rid}).status_code == 409
    r = c.post("/api/library/still", headers=tma(3), json={"code": code, "report": rid}).json()
    assert r["table"]["seats"][0] == "free" and c.get("/api/library", headers=tma(2)).json()["mine"] is None
    assert c.post("/api/library/still", headers=tma(3), json={"code": code, "report": rid}).status_code == 409  # no second round
    still = con.execute("SELECT * FROM bot_outbox WHERE kind = 'lib_still'").fetchone()
    assert still["user_id"] == ann["id"] and outbox._render(con, {**dict(still), "lang": "kk"})[2] == "lib"

    # the holder is back at once, the seat still free: the report was false, the seat hers again
    assert c.post("/api/library/sit", headers=tma(2), json={"code": code, "seat": 1}).json()["table"]["seats"][0] == "mine"
    assert con.execute("SELECT false_at FROM lib_reports WHERE id = ?", (rid,)).fetchone()[0] == t0
    assert c.get("/api/library", headers=tma(3)).json()["report"] is None
    assert outbox._render(con, {**dict(still), "lang": "kk"}) is None
    # whoever sits on a seat is never evicted by a rescan (a saved photo of the sticker)
    c.post("/api/library/sit", headers=tma(4), json={"code": code, "seat": 3, "consent": "lib1"})
    assert c.post("/api/library/sit", headers=tma(2), json={"code": code, "seat": 3}).status_code == 409
    c.post("/api/library/leave", headers=tma(4))

    # no answer in 10 minutes: the seat frees, and the reporter hears of it
    c.post("/api/library/sit", headers=tma(4), json={"code": code, "seat": 2, "consent": "lib1"})
    c.post("/api/library/report", headers=tma(3), json={"code": code, "seat": 2})
    set_clock(monkeypatch, lambda: t0 + logic.library.CONFIRM + 1)
    assert c.get("/api/library", headers=tma(3)).json()["report"]["state"] == "freed"
    assert c.get("/api/library", headers=tma(4)).json()["mine"] is None
    assert c.post("/api/library/table", headers=tma(3), json={"code": code}).json()["seats"][1] == "free"
    freed = con.execute("SELECT * FROM bot_outbox WHERE kind = 'lib_freed' ORDER BY id DESC").fetchone()
    assert freed["user_id"] == bob["id"] and freed["send_after"] == t0 + logic.library.CONFIRM
    assert outbox._render(con, {**dict(freed), "lang": "ru"})[2] == "lib"
    assert c.post("/api/library/sit", headers=tma(3), json={"code": code, "seat": 2}).json()["table"]["seats"][1] == "mine"

    # three false reports in a week: no reporting until the oldest is a week old
    con.execute("UPDATE lib_reports SET false_at = ? WHERE reporter_id = ?", (t0, bob["id"]))               # his two
    con.execute("""INSERT INTO lib_reports (sit_id, reporter_id, created_at, false_at)
        SELECT sit_id, reporter_id, created_at, false_at FROM lib_reports WHERE id = ?""", (rid,))      # and a third
    r = c.post("/api/library/report", headers=tma(3), json={"code": code, "seat": 1})
    assert r.status_code == 403 and r.json()["message"] == "strikes" and r.json()["until"] == t0 + logic.library.WEEK

    # leaving frees it; withdrawing the consent drops my seat and my records
    assert c.post("/api/library/leave", headers=tma(3)).json()["mine"] is None
    assert c.delete("/api/library/consent", headers=tma(2)).status_code == 204
    # her seat freed; only the sit under bob's "still not here" stays its week (his strike rests on it)
    assert con.execute("SELECT COUNT(*) FROM lib_sits WHERE user_id = ? AND ended_at IS NULL", (ann["id"],)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM lib_sits WHERE user_id = ?", (ann["id"],)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM lib_reports WHERE false_at IS NOT NULL").fetchone()[0] == 3
    assert c.get("/api/me", headers=tma(2)).json()["library"] == {"consent": False}

    # a week on, the night's sweep keeps nothing older
    set_clock(monkeypatch, lambda: t0 + logic.library.KEEP + 4 * 3600)
    logic.library.sweep(con)
    assert con.execute("SELECT COUNT(*) FROM lib_sits").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM lib_reports").fetchone()[0] == 0
    con.close()


def test_library_admin(env, monkeypatch):
    c, cfg = env
    boss = login(c, 1, "boss")
    login(c, 2, "ann")
    con = db.connect(cfg.db_path)
    _on(c, cfg, monkeypatch)
    room = _setup(c, con, boss["id"])
    t1, t2 = room["tables"][0], room["tables"][1]
    c.post("/api/library/sit", headers=tma(2), json={"code": t1["code"], "seat": 4, "consent": "lib1"})
    # fewer seats free the ones past the count; a removed table is no table, and comes back with Undo
    got = c.patch(f"/api/admin/library/tables/{t1['id']}", headers=tma(1), json={"seats": 2, "label": "A1"}).json()
    assert got[0]["tables"][0]["seats"] == ["free", "free"] and got[0]["tables"][0]["label"] == "A1"
    assert c.get("/api/library", headers=tma(2)).json()["mine"] is None
    c.patch(f"/api/admin/library/tables/{t2['id']}", headers=tma(1), json={"gone": True})
    assert c.post("/api/library/table", headers=tma(2), json={"code": t2["code"]}).status_code == 404
    assert len(c.patch(f"/api/admin/library/tables/{t2['id']}", headers=tma(1), json={"gone": False}).json()[0]["tables"]) == 3
    one = c.post(f"/api/admin/library/rooms/{room['id']}/tables", headers=tma(1), json={"seats": 6, "label": "Big"}).json()
    assert [t["label"] for t in one[0]["tables"]][-1] == "Big"
    assert c.post(f"/api/admin/library/rooms/{room['id']}/tables", headers=tma(1), json={"seats": 13}).status_code == 400

    # the sticker sheet: the app's pages, put together as a PDF into the admin's chat with the bot
    sent = []

    class Answer:
        status_code = 200

        def json(self):
            return {"ok": True}

    async def fake_tg(_cfg, _http, method, payload, files=None, **_):
        sent.append((method, payload, files))
        return Answer()

    monkeypatch.setattr(bot, "_tg", fake_tg)
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (124, 175), "white").save(buf, "JPEG")
    page = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    url = f"/api/admin/library/rooms/{room['id']}/stickers"
    assert c.post(url, headers=tma(2), json={"pages": [page]}).status_code == 403
    assert c.post(url, headers=tma(1), json={"pages": ["bm90IGFuIGltYWdl"]}).status_code == 400
    assert c.post(url, headers=tma(1), json={"pages": [page, page]}).status_code == 204
    (method, payload, files), = sent
    name, pdf, mime = files["document"]
    assert method == "sendDocument" and mime == "application/pdf" and pdf.startswith(b"%PDF") and payload["caption"].startswith("🖨")

    # a removed room takes its tables with it
    c.patch(f"/api/admin/library/rooms/{room['id']}", headers=tma(1), json={"gone": True})
    assert c.get("/api/library", headers=tma(2)).json()["rooms"] == []
    assert c.get(f"/api/library/screen/{room['screen']}").status_code == 404
    con.close()


def test_library_account_deletion(env, monkeypatch):
    c, cfg = env
    boss, ann, bob = login(c, 1, "boss"), login(c, 2, "ann"), login(c, 3, "bob")
    con = db.connect(cfg.db_path)
    _on(c, cfg, monkeypatch)
    code = _setup(c, con, boss["id"])["tables"][0]["code"]
    c.post("/api/library/sit", headers=tma(2), json={"code": code, "seat": 1, "consent": "lib1"})
    c.post("/api/library/report", headers=tma(3), json={"code": code, "seat": 1, "consent": "lib1"})
    delete_now(c, cfg, tma(3))
    delete_now(c, cfg, tma(2))
    for table, col, uid in (("lib_sits", "user_id", ann["id"]), ("lib_reports", "reporter_id", bob["id"]), ("lib_consents", "user_id", ann["id"])):
        assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (uid,)).fetchone()[0] == 0
    con.close()
