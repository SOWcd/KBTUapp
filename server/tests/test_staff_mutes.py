"""Admin -> My notifications: a staff member mutes a work item for themselves; muted by all, the owner still gets it."""
from __future__ import annotations

from kbtu import bot, db, logic, texts
from test_core import DB, env, login, tma  # noqa: F401  (env: the fixture)


def test_mutes(env):
    c, _ = env
    owner, adm, mod = (login(c, i, n)["id"] for i, n in ((1, "own"), (2, "adm"), (3, "mod")))
    con = db.connect(DB[0])
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE id = ?", (owner,))
    con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (adm,))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (mod,))
    assert c.get("/api/admin/notifications", headers=tma(4)).status_code == 403
    kinds = [x["kind"] for x in c.get("/api/admin/notifications", headers=tma(3)).json()]
    assert kinds == ["chat_suggested", "tgc_queue", "fch_appeal", "fch_reply_queue"]          # a moderator's own kinds
    assert c.put("/api/admin/notifications/club_application", headers=tma(3), json={"on": False}).status_code == 400
    assert "backup" in [x["kind"] for x in c.get("/api/admin/notifications", headers=tma(2)).json()]
    put = lambda uid, kind, on: c.put(f"/api/admin/notifications/{kind}", headers=tma(uid), json={"on": on})  # noqa: E731
    assert {x["kind"]: x["on"] for x in put(1, "club_application", False).json()}["club_application"] is False
    sent = lambda kind, ref: {r[0] for r in con.execute("SELECT user_id FROM bot_outbox WHERE kind = ? AND ref = ?", (kind, ref))}  # noqa: E731
    logic.notify_staff(con, [owner, adm], "club_application", "capp:1")
    assert sent("club_application", "capp:1") == {adm}                                         # the owner muted it
    put(2, "club_application", False)
    logic.notify_staff(con, [owner, adm], "club_application", "capp:2")
    assert sent("club_application", "capp:2") == {owner}                                       # all muted: the owner still hears
    put(1, "club_application", True)
    logic.notify_staff(con, [owner, adm], "club_application", "capp:3")
    assert sent("club_application", "capp:3") == {owner}
    put(2, "backup", False)
    logic.notify_staff(con, [owner, adm], "backup_failed", "bf:x")
    assert sent("backup_failed", "bf:x") == {owner}                                            # both backup messages, one switch
    logic.notify_staff(con, [], "tgc_queue", "tq:1")
    assert not sent("tgc_queue", "tq:1")                                                       # nobody to tell: not the owner either
    # deleting the account takes the mutes along
    assert con.execute("SELECT 1 FROM staff_mutes WHERE user_id = ?", (adm,)).fetchone()
    assert ("staff_mutes", "user_id") in logic._DEL_GONE


def test_appeal_text():
    for n, kind in ((1, "fch_appeal"), (2, "fch_appeal_few"), (5, "fch_appeal_many"), (11, "fch_appeal_many"), (21, "fch_appeal_one"),
                    (22, "fch_appeal_few"), (12, "fch_appeal_many")):
        assert bot._appeal_kind(n) == kind
    assert texts.bot_message("ru", "fch_appeal", n=1)[0].startswith("\U0001f6e1 1 \u043f\u043e\u0441\u0442 \u0436\u0434\u0451\u0442")
    for lang in ("ru", "kk", "en"):
        for k in ("fch_appeal", "fch_appeal_one", "fch_appeal_few", "fch_appeal_many"):
            assert "{n}" in texts.BOT[lang][k][0] and texts.BOT[lang][k][1]
