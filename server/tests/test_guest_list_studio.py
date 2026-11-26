"""The organizers load their own guest list in Studio (logic.guests.load through organizing.guest_list), add a walk-in
at the door and take the list out as a CSV after the event."""
import codecs
import json

from kbtu import logic, texts
from kbtu.logic import guests
from test_core import _club_runs, env, login, tma  # noqa: F401
from test_guest_list import _student, door_event  # noqa: F401

URL = "/api/events/1/guest-list"
DOOR = "/api/events/1/door-pending"


def _rows(*rows):
    """[name, student ID, 18+, username, team] each, missing cells empty."""
    return [list(r) + [""] * (5 - len(r)) for r in rows]


def _list(c, rows, save=True, who=9):
    return c.post(URL, headers=tma(who), json={"rows": rows, "save": save})


def test_preview_writes_nothing_and_save_matches(door_event):
    c, cfg, con = door_event
    uid = _student(c, con, 1, "24B030001")
    con.execute("UPDATE students SET last_name = 'Testov' WHERE user_id = ?", (uid,))
    other = _student(c, con, 2, "24B030009")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', '1-OTHER', 0, 0)", (other,))
    table = _rows(["Jane Testov", "24b030001", "1", "", "Owls"], ["Ivan Petrov", "24B030002", "\u043d\u0435\u0442"],
                  ["Out Sider", "", "", "@outsider_nick", "Owls"], ["Name Only"], ["Ivan Petrov", "24B030002"],
                  ["", "24B030003"], ["Bad Id", "12"], ["Bad Age", "", "maybe"], ["Bad Nick", "", "", "a b"])
    preview = _list(c, table, save=False).json()
    assert preview == {"rows": 4, "inApp": 1, "onList": 3, "dupes": 1, "dropped": 1, "removed": 0, "badCount": 4,
                       "bad": [{"row": 6, "why": "name"}, {"row": 7, "why": "student_id"}, {"row": 8, "why": "adult"}, {"row": 9, "why": "username"}]}
    # the dry run left everything as it was
    assert not con.execute("SELECT guest_list FROM events WHERE id = 1").fetchone()[0]
    assert not con.execute("SELECT 1 FROM event_guests").fetchone()
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (other,)).fetchone()[0] == "going"
    assert not con.execute("SELECT 1 FROM audit_log WHERE action = 'guest_list'").fetchone()

    assert _list(c, table).json() == preview
    assert con.execute("SELECT guest_list, age_check FROM events WHERE id = 1").fetchone()[:] == (1, 1)
    assert con.execute("SELECT status, door_team FROM registrations WHERE user_id = ?", (uid,)).fetchone()[:] == ("going", "Owls")
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (other,)).fetchone()[0] == "cancelled"
    names = {x["name"]: x for x in c.get(DOOR, headers=tma(9)).json()["list"]}
    assert set(names) == {"Ivan Petrov", "Out Sider", "Name Only"} and names["Out Sider"]["team"] == "Owls"
    assert names["Ivan Petrov"]["adult"] is False
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'guest_list'").fetchone()[0] == 1


def test_reupload_keeps_checkins_and_age_marks(door_event):
    c, cfg, con = door_event
    first = _rows(["Ivan Petrov", "24B030002", "1"], ["Came Early"], ["Not Coming"], ["Stays Here"])
    assert _list(c, first).status_code == 200
    keys = {x["name"]: x["key"] for x in c.get(DOOR, headers=tma(9)).json()["list"]}
    # the door lets in Ivan (marked under 18 from his ID card) and Came Early
    assert c.post(f"{DOOR}/tick", headers=tma(9), json={"key": keys["Ivan Petrov"], "adult": False}).status_code == 200
    assert c.post(f"{DOOR}/tick", headers=tma(9), json={"key": keys["Came Early"]}).status_code == 200
    # the corrected file: Came Early and Not Coming are gone from it, Ivan's 18+ says yes again
    out = _list(c, _rows(["Ivan Petrov", "24B030002", "1"], ["Stays Here", "", "", "", "Owls"], ["New Person"])).json()
    assert out["removed"] == 1  # Not Coming; Came Early already came: the door's record stays
    got = {x["name"]: x for x in c.get(DOOR, headers=tma(9)).json()["list"]}
    assert set(got) == {"Ivan Petrov", "Came Early", "Stays Here", "New Person"}
    assert got["Ivan Petrov"]["came"] and got["Ivan Petrov"]["adult"] is False  # the door's mark beats the sheet
    assert got["Came Early"]["came"] and got["Stays Here"]["team"] == "Owls" and got["Stays Here"]["key"] == keys["Stays Here"]
    # a new row never takes a removed row's key
    assert len({x["key"] for x in got.values()}) == 4


def test_rights_and_other_club_refused(door_event):
    c, cfg, con = door_event
    table = _rows(["Name Only"])
    _student(c, con, 1, "24B030001")
    assert _list(c, table, who=1).status_code == 403  # no door right
    _club_runs(c, con, 8, "other", slug="other")  # runs another club's door
    for save in (False, True):
        assert _list(c, table, save=save, who=8).status_code == 403
    assert c.post(f"{URL}/export", headers=tma(8)).status_code == 403
    assert c.post(f"{DOOR}/walk-in", headers=tma(8), json={"name": "Walk In"}).status_code == 403
    assert not con.execute("SELECT 1 FROM event_guests").fetchone()
    assert c.post(URL, headers=tma(9), json={"rows": table, "save": True}).status_code == 200


def test_door_helper_cannot_load_a_list(door_event):
    """A temporary door helper runs the door but never loads a list: saving one would take every sign-up's seat,
    paid ones too, and hand out tickets."""
    c, cfg, con = door_event
    paid = _student(c, con, 2, "24B030009")
    con.execute("INSERT INTO registrations (event_id, user_id, status, ticket_code, created_at, updated_at) VALUES (1, ?, 'going', '1-PAID', 0, 0)", (paid,))
    helper = _student(c, con, 5, "24B030006")
    con.execute("""INSERT INTO event_crew (event_id, user_id, org_id, kind, added_by, created_at)
        SELECT id, ?, org_id, 'door', (SELECT id FROM users WHERE tg_id = 9), 0 FROM events WHERE id = 1""", (helper,))
    for save in (False, True):
        assert _list(c, _rows(["Name Only"]), save=save, who=5).status_code == 403
    assert not con.execute("SELECT guest_list FROM events WHERE id = 1").fetchone()[0]
    assert con.execute("SELECT status FROM registrations WHERE user_id = ?", (paid,)).fetchone()[0] == "going"


def test_limits(door_event):
    c, cfg, con = door_event
    too_many = _rows(*[[f"Person {i}"] for i in range(guests.LIST_ROWS + 1)])
    r = _list(c, too_many, save=False)
    assert r.status_code == 400 and r.json()["message"] == "too_many"
    huge = json.dumps({"rows": _rows(*[["x" * 190] * 5 for _ in range(2500)])})
    assert len(huge) > 2_000_000
    assert c.post(URL, headers={**tma(9), "Content-Type": "application/json"}, content=huge).status_code == 400
    for bad in ({"rows": "nope"}, {"rows": [["a", "b"]]}, {"rows": [[1, 2, 3, 4, 5]]}, {"rows": []}, [1], {"rows": _rows(["", "", "1"])}):
        assert c.post(URL, headers=tma(9), json=bad).status_code == 400, bad
    long = _list(c, _rows(["y" * 300], ["Fine Name"]), save=False).json()
    assert long["bad"] == [{"row": 1, "why": "long"}] and long["rows"] == 1
    assert not con.execute("SELECT 1 FROM event_guests").fetchone()


def test_formula_text_stays_plain(door_event):
    c, cfg, con = door_event
    evil = '=HYPERLINK("http://x","click")'
    assert _list(c, _rows([evil, "", "", "", "+cmd|' /C calc'!A0"])).status_code == 200
    assert con.execute("SELECT name, team FROM event_guests").fetchone()[:] == (evil, "+cmd|' /C calc'!A0")
    name, data, caption = texts.guest_list_csv("en", "Paper tickets", [{**g, "app": False} for g in guests.export(con, 1)])
    head, row = data.decode("utf-8-sig").splitlines()
    assert data.startswith(codecs.BOM_UTF8) and caption == "Guest list: Paper tickets" and name == "guests.csv"
    assert row.split(";")[0].startswith("\"'=HYPERLINK") and "'+cmd" in row


def test_walk_in_at_the_door(door_event):
    c, cfg, con = door_event
    assert c.post(f"{DOOR}/walk-in", headers=tma(9), json={"name": "Walk In"}).status_code == 404  # not a guest-list event
    assert _list(c, _rows(["Listed Person", "", "1"])).status_code == 200
    r = c.post(f"{DOOR}/walk-in", headers=tma(9), json={"name": "  Walk   In ", "team": "Owls", "adult": True}).json()
    assert r["name"] == "Walk In" and r["came"] and r["walkIn"] and r["adult"] is True and r["team"] == "Owls"
    assert r["pendingCame"] == 1 and r["pending"] == 2
    _student(c, con, 1, "24B030001")
    assert c.post(f"{DOOR}/walk-in", headers=tma(1), json={"name": "Sneaky"}).status_code == 403
    for bad in ({"name": ""}, {"name": 5}, {"name": "A", "adult": "yes"}, {"name": "x" * 121}, {"name": "Ok Name", "team": "t" * 81}):
        assert c.post(f"{DOOR}/walk-in", headers=tma(9), json=bad).status_code == 400, bad
    # no 18+ asked when the event doesn't check age
    con.execute("UPDATE events SET age_check = 0 WHERE id = 1")
    assert c.post(f"{DOOR}/walk-in", headers=tma(9), json={"name": "No Age", "adult": False}).json()["adult"] is None
    # a corrected list never removes them; the door is shut after the end
    _list(c, _rows(["Listed Person"]))
    got = {x["name"]: x for x in c.get(DOOR, headers=tma(9)).json()["list"]}
    assert got["Walk In"]["walkIn"] and got["No Age"]["came"]
    end = logic.now() - 1
    con.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = 1", (end - 3600, end))
    assert c.post(f"{DOOR}/walk-in", headers=tma(9), json={"name": "Too Late"}).status_code == 409
    assert _list(c, _rows(["Listed Person"])).status_code == 409  # a list after the end changes nothing


def test_export_after_the_event(door_event):
    c, cfg, con = door_event
    uid = _student(c, con, 1, "24B030001")
    con.execute("UPDATE students SET last_name = 'Testov' WHERE user_id = ?", (uid,))
    _list(c, _rows(["Jane Testov", "24B030001", "", "", "Owls"], ["Came Person", "", "", "", "Cats"], ["Absent Person"]))
    key = next(x["key"] for x in c.get(DOOR, headers=tma(9)).json()["list"] if x["name"] == "Came Person")
    c.post(f"{DOOR}/tick", headers=tma(9), json={"key": key})
    c.post(f"{DOOR}/walk-in", headers=tma(9), json={"name": "Walk In"})
    me = c.get("/api/me", headers=tma(9)).json()["id"]
    e, people = logic.organizing.guest_list_export(con, logic.Viewer(me, "user", True), 1)
    _, data, _ = texts.guest_list_csv("en", e["title"], people)
    lines = data.decode("utf-8-sig").splitlines()
    assert lines[0].split(";") == list(texts.GUEST_LIST_HEAD["en"])
    rows = {r.split(";")[0]: r.split(";") for r in lines[1:]}
    assert rows["Came Person"][1:3] == ["Cats", "yes"] and rows["Came Person"][3] and rows["Came Person"][4] == "list"
    assert rows["Absent Person"][2:] == ["no", "", "list"]
    assert rows["Walk In"][2] == "yes" and rows["Walk In"][4] == "added at the door"
    assert any(r[4] == "app" and r[1] == "Owls" for r in rows.values())
    assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'guest_list_export'").fetchone()[0] == 1
    # nobody else gets it
    assert c.post(f"{URL}/export", headers=tma(1)).status_code == 403


def test_export_names_as_the_door_list_does(door_event):
    """A Member with the door right sees the sheet's short names at the door; the CSV must not hand them the whole ones."""
    c, cfg, con = door_event
    _list(c, _rows(["Testova Jane Middle", "", "", "", "Owls"]))
    member = _student(c, con, 1, "24B030001")
    org = con.execute("SELECT org_id FROM events WHERE id = 1").fetchone()[0]
    con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (?, ?, 'member', 0)", (org, member))
    assert [x["name"] for x in c.get(DOOR, headers=tma(1)).json()["list"]] == ["Jane T"]
    _, people = logic.organizing.guest_list_export(con, logic.Viewer(member, "user", True), 1)
    assert [p["name"] for p in people if not p["app"]] == ["Jane T"]
    # who runs the events keeps the whole name, at the door and in the CSV
    me = c.get("/api/me", headers=tma(9)).json()["id"]
    _, people = logic.organizing.guest_list_export(con, logic.Viewer(me, "user", True), 1)
    assert [p["name"] for p in people if not p["app"]] == ["Testova Jane Middle"]
