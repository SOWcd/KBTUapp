"""Lanyards: the clubs' (the server's logic.LANYARDS and the web's awards.ts SKINS + CLUB_LOOKS are one) and the schools'."""
import re
from pathlib import Path

from kbtu import db, logic
from test_core import env, login, tma  # noqa: F401  (env: the fixture)

AWARDS = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "awards.ts"


def test_lanyards_match_the_web():
    src = AWARDS.read_text()
    hand = re.search(r"const SKINS = \{(.*?)\} as const", src, re.S).group(1)
    looks = re.search(r"export const CLUB_LOOKS = \{(.*?)\n\} satisfies", src, re.S).group(1)
    web = re.findall(r"(\w+): '\w+'", hand) + re.findall(r"^  (\w+): \{", looks, re.M)
    assert len(web) == len(set(web)) and set(web) == set(logic.LANYARDS)
    schools = re.search(r"export const SCHOOL_LOOKS = \{(.*?)\n\} satisfies", src, re.S).group(1)
    assert set(re.findall(r"^  (\w+): \{", schools, re.M)) == set(logic.SCHOOL_LANYARDS)


def test_school_slug():
    """A student's school as prod writes it (the portal's full names and abbreviations, Settings' names) to its org."""
    cases = {"\u0428\u0418\u0422\u0438\u0418": "site", "\u0428\u043a\u043e\u043b\u0430 \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u043e\u043d\u043d\u044b\u0445 \u0442\u0435\u0445\u043d\u043e\u043b\u043e\u0433\u0438\u0439 \u0438 \u0438\u043d\u0436\u0435\u043d\u0435\u0440\u0438\u0438": "site",
             "\u0428\u042d\u0438\u041d\u0413\u0418": "seogi", "\u0411\u0428": "business", "\u0411\u0438\u0437\u043d\u0435\u0441 \u0448\u043a\u043e\u043b\u0430": "business", "\u0428\u0425\u0418": "sce",
             "\u0428\u041c\u0438\u0417\u0422": "smsgt", "\u0428\u0413": "geology", "\u041a\u041c\u0410": "kma", "\u0428\u041f\u041c": "sam", "\u041c\u0428\u042d": "ise",
             "\u0428\u043a\u043e\u043b\u0430 \u043f\u0440\u0430\u0432\u0430": "law", "\u0428\u043a\u043e\u043b\u0430 \u0441\u043e\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0445 \u043d\u0430\u0443\u043a": "sss",
             " site ": "site", "\u0414\u0418\u0422": None, "": None, None: None}
    assert {k: logic.school_slug(k) for k in cases} == cases
    assert set(logic.SCHOOL_LANYARDS) == {s["slug"] for s in logic.SCHOOLS}


def test_school_lanyard(env):
    """A school's lanyard is its own students' alone, with no joining, and mine by default; a school no longer mine falls back to KBTU's."""
    c, cfg = env
    ann, bob = login(c, 80, "ann"), login(c, 81, "bob")                 # both SITE (login)
    con = db.connect(cfg.db_path)
    site, ise = 1, 2
    con.execute("""INSERT INTO orgs (id, slug, kind, name, short, emoji, official, created_at) VALUES (1, 'site', 'school', 'IT', 'IT', 'laptop_3d', 1, 0),
        (2, 'ise', 'school', 'ISE', 'IS', 'laptop_3d', 1, 0)""")
    con.execute("UPDATE students SET school = 'ISE' WHERE user_id = ?", (bob["id"],))
    con.commit()
    A, B = tma(80, "Ann"), tma(81, "Bob")
    assert c.get("/api/me", headers=A).json()["skin"] == site          # never picked: my school's comes by itself (owner, Nov 2)
    assert c.patch("/api/me", headers=A, json={"skin": None}).json()["skin"] is None   # KBTU's picked: it stays
    assert c.patch("/api/me", headers=A, json={"skin": site}).json()["skin"] == site
    assert c.patch("/api/me", headers=A, json={"skin": ise}).status_code == 400   # not my school
    assert c.patch("/api/me", headers=B, json={"skin": site}).status_code == 400
    assert c.get(f"/api/users/{ann['id']}", headers=B).json()["skin"] == site    # others see it
    con.execute("UPDATE students SET school = NULL WHERE user_id = ?", (ann["id"],))
    con.commit()
    assert c.get("/api/me", headers=A).json()["skin"] is None          # no school any more: KBTU's
