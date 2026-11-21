# When the bot may send someone's words

The rule (AGENTS.md): the bot sends templates with a button into the app, never a user's words. The exceptions, all of them:

Two exceptions: a student's own post
to the forum channel (`FORUM_CHANNEL`), published only after the AI's yes or a moderator's, as plain text without
links or mentions, signed with the app's name or "Anonymous student"; the author can delete it, a moderator can
take it down, and only the creator can reveal an anonymous author (audit log). The author of an anonymous post may
reply in its comments the same way (`fchan_replies`): plain text, its own AI check, signed
with the mask mark (`texts.FCH_REPLY_SIGN`), no user id on the row (only through the post), deleted by the author,
taken down from Admin. In a group, `/all` (anyone Telegram says is in the chat and who has a student's account in the app may call, never in a channel's discussion group; it mentions the app's list, whom the bot saw and the chat's members it lists over MTProto as itself, `kbtu/mtbot.py`, kept nowhere, a hidden roster only for an admin's call; their words never become a mention or a link) repeats the caller's own words over each five mentions, in the very chat they wrote them (escaped, short). And a user's own text going back to them alone: a channel comment a moderator restored
(`tgc_back`, to post it again), the title of my own find-people request (`contact_ask`, `ask_hidden`).
A share card of a forum post live in the channel (`/api/share` kind `fp`, inline mode) quotes its first 160 characters,
escaped, never a signature; inline offers only my own signed posts. A card already sent stays in its chat after a
take-down, as a forward of the channel's post would.

Also: in a group, a TikTok, YouTube Shorts or Instagram link is answered with the video file itself (`TIKTOK=1`, `kbtu/tiktok.py`), no caption, no words of the bot's own.
