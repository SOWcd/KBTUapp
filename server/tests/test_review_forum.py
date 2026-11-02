"""Review findings (forum channel anonymity, schedule name match): each test fails on the code as reviewed."""
from __future__ import annotations

import pytest

from kbtu import db, logic, portal
from test_core import delete_now, env, login, tma  # noqa: F401  (env: the fixture)
from test_fchannel import Telegram, setup, tick


@pytest.mark.xfail(strict=True, reason="needs the owner: the policy says posts leave the app at once; keeping the anonymous ones until their own channel deletion changes that wording (a new consent version)")
def test_deleted_account_anon_post_not_dropped_from_feed_with_named(env, monkeypatch):
    """Deleting an account spreads its anonymous posts' channel deletions over 3 days so they can't be linked to its
    named ones. But the rows go at once, so every student's Forum tab loses the named and the anonymous post in the
    same instant: whoever polls the feed links them anyway."""
    c, cfg, _, _ = setup(env, monkeypatch)
    login(c, 1, "ann"), login(c, 2, "bob")
    con = db.connect(cfg.db_path)
    c.post("/api/forum-posts", headers=tma(1), json={"body": "My named words here"})
    tick(cfg, Telegram(), con)
    con.execute("""INSERT INTO fchan_posts (user_id, body, anon, status, tg_msg, created_at)
        SELECT user_id, 'an anonymous one', 1, 'live', 777, created_at FROM fchan_posts""")
    before = {p["body"] for p in c.get("/api/forum-posts/feed", headers=tma(2)).json()}
    assert before == {"My named words here", "an anonymous one"}
    delete_now(c, cfg, tma(1))
    after = {p["body"] for p in c.get("/api/forum-posts/feed", headers=tma(2)).json()}
    # the anonymous one must stay up in the app until its own moment in the channel, not vanish with the named one
    assert "an anonymous one" in after
    con.close()


@pytest.mark.parametrize("dash", ["\u2500", "\u2501", "\u2e3a"])  # box drawing light, heavy; two-em dash
def test_signature_lookalike_dash_refused(dash):
    """An anonymous post posing as a named one: a last line "<dash> Dana S" is refused, but box-drawing and two-em
    dashes (identical to the bot's em dash on screen; NFKC doesn't fold them) pass."""
    with pytest.raises(logic.ApiError):
        logic.fchannel._clean(f"I saw it all\n{dash} Dana S")


def test_schedule_full_name_with_another_first_name():
    """A page's full name "Testov Ali" is Ali Testov's; Bek Testov (same surname) passes the check and gets Ali's week:
    only initials are compared with the other name, a whole other first name never is."""
    assert portal.same_person("Testov Ali", "Ali", "Testov")
    assert not portal.same_person("Testov Ali", "Bek", "Testov")
    assert not portal.same_person("Ali Testov", "Bek", "Testov")
    assert portal.same_person("Testov Ali Serikovich", "Ali", "Testov")  # a patronymic still passes
