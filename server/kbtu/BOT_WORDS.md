# When the bot may send someone's words

The rule (AGENTS.md): the bot sends templates with a button into the app, never a user's words. The exceptions, all of them:

Two exceptions: a student's own post
to the forum channel (`FORUM_CHANNEL`), published only after the AI's yes or a moderator's, as plain text without
links or mentions, signed with the app's name or "Anonymous student"; the author can delete it, a moderator can
take it down, and only the creator can reveal an anonymous author (audit log). The author of an anonymous post may
reply in its comments the same way (`fchan_replies`): plain text, its own AI check, signed
with the mask mark (`texts.FCH_REPLY_SIGN`), no user id on the row (only through the post), deleted by the author,
taken down from Admin. A verified student may also comment under any live post from the app (`fchannel.comment_*`, same
table, same AI check, same moderators and take-downs): plain text, signed with their short name as a named post is, the
row keeps their user id (an anonymous author's reply never does), the author deletes it, a deleted account's go out of the group. In a group, `/all` (a verified student who Telegram says is in the chat may call if they administer the group or hold a leadership or assigned role in the club that owns the chat, never in a channel's discussion group; it mentions the app's list, whom the bot saw and the chat's members it lists over MTProto as itself, `kbtu/mtbot.py`, kept nowhere, a hidden roster only for an admin's call; their words never become a mention or a link) repeats the caller's own words over each five mentions, in the very chat they wrote them (escaped, short). And a user's own text going back to them alone: a channel comment a moderator restored
(`tgc_back`, to post it again), the title of my own find-people request (`contact_ask`, `ask_hidden`).
A share card of a forum post live in the channel (`/api/share` kind `fp`, inline mode) quotes its first 160 characters,
escaped, never a signature; inline offers only my own signed posts. A card already sent stays in its chat after a
take-down, as a forward of the channel's post would. Outside the Mini App (a browser, the phone apps) the same card,
built by `/api/share` (`handoff`), waits an hour in `meta` under a one-time secret (`core.share_hold`): the bot sends it
only to the Telegram account that made it, in its private chat (`/start sh_<secret>`), and its "Send to a chat" button
offers it in inline mode to that account alone; no new words.

Also: in a group, a TikTok, YouTube Shorts or Instagram link is answered with the video file itself, or the post's photos and videos as one album (`TIKTOK=1`, `kbtu/tiktok.py`; an Instagram story's video only with `INSTAGRAM_COOKIES`), no caption, no words of the bot's own.

The CSV exports use template captions and go to the requester's private chat with the bot. Attendee exports may contain sign-up answers. Team log exports include attendance comments for people with current report consent and require the club's `reports` right.
