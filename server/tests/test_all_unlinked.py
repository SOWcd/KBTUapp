"""/all in a chat no club holds (owner, Nov 14): its Telegram admin calls whom the bot saw there."""
from kbtu import db
from kbtu.logic import chatlist
from test_core import env  # noqa: F401  (env: the fixture)


def test_unlinked_chat_remembers_and_admin_calls(env):  # noqa: F811
    _, cfg = env
    con = db.connect(cfg.db_path)
    chatlist._unheld.clear()
    for tg in (101, 102, 103):
        chatlist.seen(con, -500, {"id": tg})
    assert chatlist.tag_all(con, -500, 101) == []                       # not an admin: nobody
    assert set(chatlist.tag_all(con, -500, 101, admin=True)) == {102, 103}  # never the caller
    chatlist.unseen(con, -500, 102)
    assert chatlist.tag_all(con, -500, 101, admin=True) == [103]
