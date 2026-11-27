"""Admin CLI confirmations, user lookup, and clean argument failures."""
import base64
import gzip
import json

import pytest

from helpers import env, login, tma  # noqa: F401
from kbtu import admin, config, db, logic


@pytest.fixture
def cli(env, monkeypatch):
    c, cfg = env
    monkeypatch.setattr(config, "load", lambda: cfg)
    con = db.connect(cfg.db_path)
    yield c, con
    con.close()


def _packed(raw):
    return base64.b64encode(gzip.compress(raw)).decode()


def test_duplicate_telegram_username(cli):
    c, con = cli
    first, second = login(c, 10, "first"), login(c, 11, "second")
    login(c, 12, "admin")
    con.execute("UPDATE users SET role = 'admin' WHERE tg_id = 12")
    con.execute("UPDATE users SET tg_username = 'Duplicate' WHERE tg_id = 10")
    con.execute("UPDATE users SET tg_username = 'duplicate' WHERE tg_id = 11")
    admin.main(["org", "chess", "Chess Club", "CH", "laptop_3d"])
    oid = con.execute("SELECT id FROM orgs WHERE slug = 'chess'").fetchone()[0]
    who = "@DUPLICATE"
    for args in (["move", who, "12", "--yes"], ["move", "12", who, "--yes"], ["unlink", who, "--yes"],
                 ["staff", who, "--yes"], ["founder", who, "--yes"], ["role", who, "chess", "head"],
                 ["unseat", who, "1"], ["fix", who, "reset"], ["mark", who, "idea"]):
        with pytest.raises(SystemExit, match="use the Telegram ID"):
            admin.main(args)
    url = f"/api/admin/orgs/{oid}/role"
    response = c.put(url, headers=tma(12), json={"who": who, "role": "head"})
    assert response.status_code == 400 and response.json()["error"] == "bad_input"
    assert "use the Telegram ID" in response.json()["message"]
    assert not con.execute("SELECT 1 FROM org_members WHERE org_id = ?", (oid,)).fetchone()
    assert c.put(url, headers=tma(12), json={"who": "11", "role": "head"}).status_code == 200
    admin.main(["mark", "10", "idea"])
    assert con.execute("SELECT mark FROM users WHERE id = ?", (first["id"],)).fetchone()[0] == "idea"
    assert con.execute("SELECT user_id FROM org_members WHERE org_id = ?", (oid,)).fetchone()[0] == second["id"]


def test_destructive_commands_default_to_no(cli, monkeypatch):
    c, con = cli
    login(c, 10, "first")
    c.get("/api/me", headers=tma(11))
    con.execute("INSERT INTO qr_sessions (id, title, pin_hash, created_at) VALUES (1, 'Test', 'test', 0)")
    prompts = []

    def decline(prompt):
        prompts.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", decline)
    monkeypatch.setattr(db, "init", lambda *_: pytest.fail("redelete started before confirmation"))
    commands = (["staff", "10"], ["staff", "11", "First", "Last"], ["founder", "10"], ["move", "10", "11"],
                ["unlink", "10"], ["redelete"], ["checkin", "expect", "1", _packed(b"[]"), "--only"],
                ["donation", "remove", "1"], ["credit", "del", "1"])
    for args in commands:
        with pytest.raises(SystemExit, match="^cancelled$"):
            admin.main(args)
    assert len(prompts) == len(commands) and all(prompt.endswith("[y/N] ") for prompt in prompts)
    assert not con.execute("SELECT 1 FROM users WHERE is_founder = 1").fetchone()

    def no_stdin(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_stdin)
    with pytest.raises(SystemExit, match="use --yes"):
        admin.main(["founder", "10"])
    admin.main(["founder", "--yes", "10"])
    assert con.execute("SELECT tg_id FROM users WHERE is_founder = 1").fetchone()[0] == 10

    monkeypatch.setattr("builtins.input", lambda _: " Y ")
    admin.main(["founder", "11"])
    founder = con.execute("SELECT id, tg_id FROM users WHERE is_founder = 1").fetchall()
    assert [row["tg_id"] for row in founder] == [11]
    assert con.execute("SELECT target FROM audit_log WHERE action = 'founder' ORDER BY id DESC LIMIT 1").fetchone()[0] == f"user:{founder[0]['id']}"


def test_move_refuses_banned_source(cli):
    c, con = cli
    first = login(c, 10, "first")
    c.get("/api/me", headers=tma(11))
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (first["id"],))
    with pytest.raises(SystemExit, match="source is banned"):
        admin.main(["move", "10", "11", "--yes"])
    assert con.execute("SELECT tg_id FROM users WHERE id = ?", (first["id"],)).fetchone()[0] == 10
    assert not con.execute("SELECT 1 FROM audit_log WHERE action = 'account_move'").fetchone()


@pytest.mark.parametrize("bad", [str(2**63), "\u0661", "\u00b2"])
def test_invalid_cli_ids(cli, bad):
    date = "2030-01-01 12:00"
    for args in (["reg-until", bad, "2030-01-01T12:00:00+05:00"], ["event-link", bad, "https://example.org"],
                 ["came", "1", bad], ["seat", "1", bad], ["unseat", "1", bad], ["u18", bad], ["u18", "1", bad],
                 ["photo-call", bad], ["checkin", "expect", bad, _packed(b"[]")], ["grant", "session", bad, "init26"],
                 ["casting", "from-event", bad, date], ["meeting", "new", "Meeting", date, bad, "Hall", "Agenda"]):
        with pytest.raises(SystemExit) as exc:
            admin.main(args)
        assert exc.value.code == admin.__doc__


def test_checkin_new_and_replace_validate_the_whole_list(cli, tmp_path, monkeypatch):
    c, con = cli
    people = tmp_path / "people.json"
    new = ["checkin", "new", "Test session", str(people)]
    with pytest.raises(SystemExit, match="readable UTF-8 JSON file"):
        admin.main(new)
    for raw in ("{", "{}", "[null]", '[{"email": true}]',
                '[{"email": "one@example.org"}, {"email": "two@example.org", "course": "first"}]'):
        people.write_text(raw, encoding="utf-8")
        with pytest.raises(SystemExit):
            admin.main(new)
    assert not con.execute("SELECT 1 FROM qr_sessions").fetchone()
    people.write_text('[{"email": "ONE@example.org", "course": "1"}, {"name": "No email"}]', encoding="utf-8")
    admin.main(new)
    sid = str(con.execute("SELECT id FROM qr_sessions").fetchone()[0])
    expected = "SELECT email FROM qr_expected ORDER BY email"
    assert [r[0] for r in con.execute(expected)] == ["one@example.org"]

    replacement = _packed(json.dumps([{"name": "Test Person", "studentId": "24B12345"}]).encode())
    expect = ["checkin", "expect", sid]
    for bad in ("!", base64.b64encode(b"not gzip").decode(), _packed(b"["), _packed(b"{}"),
                _packed(b'[{"name": "Missing ID"}]'), _packed(b'[{"name": "\\ud800", "studentId": "24B12345"}]')):
        with pytest.raises(SystemExit, match="people"):
            admin.main([*expect, bad, "--only", "--yes"])
        assert [r[0] for r in con.execute(expected)] == ["one@example.org"]
    with pytest.raises(SystemExit, match="no such session"):
        admin.main(["checkin", "expect", "999", replacement])
    admin.main([*expect, replacement[:76] + "\n" + replacement[76:]])
    assert [r[0] for r in con.execute(expected)] == ["id:24b12345", "one@example.org"]
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("--yes prompted"))
    admin.main([*expect, replacement, "--only", "--yes"])
    assert [r[0] for r in con.execute(expected)] == ["id:24b12345"]

    login(c, 10, "admin")
    con.execute("UPDATE users SET role = 'admin', is_founder = 1 WHERE tg_id = 10")
    for session, award in (("999", "init26"), (sid, "unknown")):
        with pytest.raises(SystemExit, match="refused: bad_input"):
            admin.main(["grant", "session", session, award])
    admin.main(["grant", "session", sid, "init26"])


def test_org_and_auto_publish_roll_back_when_audit_fails(cli, monkeypatch):
    _, con = cli

    def fail(*_):
        raise RuntimeError("audit failed")

    create = ["org", "chess", "Chess Club", "CH", "laptop_3d"]
    with monkeypatch.context() as patched:
        patched.setattr(logic.clubs, "log_action", fail)
        with pytest.raises(RuntimeError, match="audit failed"):
            admin.main(create)
    assert not con.execute("SELECT 1 FROM orgs WHERE slug = 'chess'").fetchone()
    admin.main(create)
    admin.main(["auto-publish", "chess", "on"])
    monkeypatch.setattr(admin, "log_action", fail)
    with pytest.raises(RuntimeError, match="audit failed"):
        admin.main(["auto-publish", "chess", "off"])
    assert con.execute("SELECT auto_publish FROM org_flags JOIN orgs ON org_id = orgs.id WHERE slug = 'chess'").fetchone()[0] == 1
