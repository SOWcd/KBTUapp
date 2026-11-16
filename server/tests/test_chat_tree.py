"""The tree of a club's groups (logic/chattree.py): main, departments, other and loose groups, sync over label, counts
only, the guess, who may see and place (a member can't, another club's leader can't, DMP Head+ and the admin see all,
nobody outside sees anything), and that a label never touches membership."""
from __future__ import annotations

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)


def _setup(c, cfg):
    for tg in (21, 22, 31, 41, 51, 52, 60):
        login(c, tg, f"u{tg}")
    con = db.connect(cfg.db_path)
    uid = lambda tg: con.execute("SELECT id FROM users WHERE tg_id = ?", (tg,)).fetchone()[0]  # noqa: E731
    oid = logic.create_org(con, None, "Chess", "CH", "crown_3d", False)
    logic.set_role(con, None, uid(21), oid, "president", "test")
    logic.set_role(con, None, uid(22), oid, "vice", "test")
    logic.set_role(con, None, uid(31), oid, "member", "test")
    other = logic.create_org(con, None, "Go", "GO", "crown_3d", False)
    logic.set_role(con, None, uid(41), other, "president", "test")
    dmp = logic.create_org(con, None, "DMP", "DM", "crown_3d", False)
    con.execute("UPDATE orgs SET can_oversee = 1, kind = 'office' WHERE id = ?", (dmp,))
    logic.set_role(con, None, uid(51), dmp, "head", "test")
    logic.set_role(con, None, uid(52), dmp, "member", "test")
    pr = con.execute("INSERT INTO org_tags (org_id, name, color, created_at, department) VALUES (?, 'Media', '#ff0000', 0, 1)", (oid,)).lastrowid
    ev = con.execute("INSERT INTO org_tags (org_id, name, color, created_at, department) VALUES (?, 'Events', '#00ff00', 0, 1)", (oid,)).lastrowid
    card = lambda title, tg, n, forum=0: con.execute("""INSERT INTO chats (title, kind, forum, url, tg_chat_id, members, created_at, status, org_id)
        VALUES (?, 'group', ?, ?, ?, ?, 0, 'org', ?)""", (title, forum, f"https://t.me/+{tg}", tg, n, oid)).lastrowid  # noqa: E731
    hub = card("Chess hub", -101, 120, 1)
    media = card("Chess Media team", -102, 14)
    synced = card("Chess events crew", -103, 9)
    con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, tag_id, last_date, created_at) VALUES (-103, ?, 'dept', ?, 500, 1)", (oid, ev))
    con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, tag_id, paused, created_at) VALUES (-104, ?, 'dept', ?, 'x', 7)", (oid, ev))
    return con, uid, oid, other, dmp, {"media": pr, "events": ev}, {"hub": hub, "media": media, "synced": synced}


def test_tree_and_rights(env):
    c, cfg = env
    con, uid, oid, other, dmp, tags, chats = _setup(c, cfg)
    get = lambda tg, o=oid: c.get(f"/api/orgs/{o}/chats/tree", headers=tma(tg))  # noqa: E731
    assert get(31).status_code == 403 and get(41).status_code == 403 and get(60).status_code == 403  # a member, another club's President, a stranger
    t = get(21).json()
    assert t["groups"] == 4 and t["kept"] == 1 and t["last"] == 500 and t["main"] is None
    ev = next(d for d in t["depts"] if d["id"] == tags["events"])
    assert [(n["title"], n["sync"], n["by"]) for n in ev["chats"]] == [("Chess events crew", "on", "sync"), (None, "paused", "sync")]
    loose = {n["id"]: n for n in t["loose"]}
    assert loose[chats["hub"]]["guess"] == {"place": "main"}                                   # a topics group, no main yet
    assert loose[chats["media"]]["guess"] == {"place": "dept", "tag": tags["media"]}           # the department's name in its title
    assert "-101" not in get(21).text and "tg_chat_id" not in get(21).text                     # no Telegram ids
    place = lambda tg, cid, body, o=oid: c.put(f"/api/orgs/{o}/chats/{cid}/place", json=body, headers=tma(tg))  # noqa: E731
    assert place(31, chats["hub"], {"place": "main"}).status_code == 403
    assert place(41, chats["hub"], {"place": "main"}).status_code == 403
    assert place(41, chats["hub"], {"place": "main"}, other).status_code == 404                # by its own club: not theirs
    assert place(21, chats["synced"], {"place": "other"}).status_code == 409                   # the sync's place holds
    assert place(21, chats["media"], {"place": "dept", "tag": 9999}).status_code == 400
    assert place(21, chats["media"], {"place": "dept"}).status_code == 400
    members = con.execute("SELECT COUNT(*) FROM org_members WHERE org_id = ?", (oid,)).fetchone()[0]
    assert place(21, chats["hub"], {"place": "main"}).json()["main"]["id"] == chats["hub"]
    t = place(22, chats["media"], {"place": "dept", "tag": tags["media"]}).json()
    assert [n["id"] for d in t["depts"] if d["id"] == tags["media"] for n in d["chats"]] == [chats["media"]] and not t["loose"]
    assert con.execute("SELECT COUNT(*) FROM org_members WHERE org_id = ?", (oid,)).fetchone()[0] == members  # a label only
    assert not con.execute("SELECT 1 FROM chat_sync WHERE chat_id IN (-101, -102)").fetchone()
    assert place(21, chats["media"], {"place": None}).json()["loose"][0]["id"] == chats["media"]
    # DMP: its Head and the admin see every organisation, DMP's own too; its plain member and a club's President don't
    assert c.get("/api/registry/chats", headers=tma(52)).status_code == 403
    assert c.get("/api/registry/chats", headers=tma(21)).status_code == 403
    all_ = c.get("/api/registry/chats", headers=tma(51)).json()
    by = {x["org"]["id"]: x for x in all_}
    assert {oid, other, dmp} <= set(by) and by[oid]["groups"] == 4 and by[other]["groups"] == 0
    # a group given to another club leaves its label behind: loose there
    con.execute("UPDATE chats SET org_id = ? WHERE id = ?", (other, chats["hub"]))
    t = c.get("/api/registry/chats", headers=tma(51)).json()
    assert {x["org"]["id"]: x for x in t}[other]["loose"][0]["id"] == chats["hub"]
    # a synced main group holds the top over a label placed before the link
    con.execute("UPDATE chats SET org_id = ? WHERE id = ?", (oid, chats["hub"]))
    assert place(21, chats["hub"], {"place": "main"}).status_code == 200
    con.execute("INSERT INTO chat_sync (chat_id, org_id, kind, created_at) VALUES (-105, ?, 'main', 1)", (oid,))
    t = get(21).json()
    assert t["main"]["by"] == "sync" and t["main"]["id"] is None and [n["id"] for n in t["other"]] == [chats["hub"]]
    assert place(21, chats["media"], {"place": "main"}).status_code == 409

