"""The app's rules over SQLite, answering in the shapes of web/src/lib/api/types.ts (camelCase).

The only copy of the rules. Every function takes the connection and the caller (`Viewer`) and either returns
JSON-ready data or raises ApiError. Writes that check and then change (seats, check-in) run in db.tx.

Split by domain into the modules beside this file; the names callers reach as kbtu.logic.X are re-exported here,
the rest stay in their module (logic.account._DEL_GONE). A test that patches the clock or a limit patches the
module that holds it (logic.core.now).
"""

from __future__ import annotations

from .core import (NAME, STUDENT_ID, ApiError, DOOR_AUTO, DOOR_LATE, door_at, door_shut, NO_END, PERSON, PERSON_COLS,
    PROFILE_QR, RANK, Viewer, _may, _once, _qs, _rights, academic_year, add_photo, can, card, course_day, course_of,
    decided, log_action, need_student, now, one, organizes, overseer, person_ref, rights_of, role_in, rows, short_name,
    shown_name, share_card, share_hold, taken)  # noqa: F401
from .seats import (_visible, add_receipt, add_seats, cal_feed, calendar_owner, cal_token,
    reset_cal_token, channel_discussion, channel_due, channel_gone, chat_claim, chat_join, chat_set, chat_start, end_of, event,
    guard_join, guard_read, guard_token, event_ics, events, ics_sig, notify, notify_staff, past_events, promote, receipt_open,
    receipt_path, register, remove_seats, review_receipt, joined, refill, signup_open, team_ask, team_asks,
    team_decide, team_unask, set_saved, sweep_holds, title_in, unregister, volunteer_apply, volunteer_decide,
    volunteer_leave, volunteers_list)  # noqa: F401
from .queues import (AI_LIMIT, ai_failed, ai_next, ai_note, ai_save, my_video, new_video, next_video, stale_videos,
    video_done, video_shape, video_uploaded)  # noqa: F401
from .account import (ARCHIVE, CONSENT, agreed, ai_on, _qr_code, ask_delete, consent, delete_due,
    delete_info, replay_deletions, drain_deleted_files, dm_on, drop_my_photo, drop_my_schedule, id_clash, keep_me,
    lent_studio, me, ms_claim, ms_hold, ms_link, ms_pending, ms_release, ms_sweep, fix_identity, sid_tries, refer,
    roster_requests, save_schedule, schedule, set_photo, update_me)  # noqa: F401
from .clubs import (OFFICIAL_ROLES, SHORT, _slug_free, add_link, apply, apply_club, create_org,
    decide_club_application, delete_org, ask_official, decide_official, official_path, decide_join, drop_link,
    fill_abbrs, join_requests, my_club_application, name_slugs, org, org_links, org_name, orgs, people, seed_schools,
    start_by_slug, strip_emoji_names, subscribe, update_org, withdraw)  # noqa: F401
from .newsfeed import (cancel_casting, castings, create_post, feature, hide_post, posts, react, read_posts,
    update_post, wipe_post)  # noqa: F401
from .chatlist import (add_chat, add_org_chat, approve_chat, bot_added, bot_admin, bot_unwait, my_waits, wait_target,
    claim_wait, tag_all, chat_pick, pick_claim, bot_left, chat_card, chat_input, chat_link, chat_opened,
    chat_refreshed, chats, chats_gone, delete_chat, drop_org_chat, main_org_chat, may_chats, mirror_org_chat, news_org_chat,
    org_chats, photo_free, set_chat_org, suggest_chat, suggest_check, chat_links, known_chat, set_chat_section,
    sort_next, sort_save, chat_asked_too)  # noqa: F401
from .oversight import (_owner, admin_create_org, admin_hide_org, admin_set_award, admin_org_events, admin_orgs,
    admin_set_role, audit, ban_info, find_people, find_user, registry, registry_export, registry_memos,
    registry_roster, registry_search, set_ban, set_official, set_role, set_staff, set_staff_mute, staff,
    staff_mutes)  # noqa: F401
from .moderation import (add_comment, close_gone, comments, delete_comment, purge_takedowns, report, report_queue,
    resolve_report, restore, set_comments_on)  # noqa: F401
from .profiles import (ACHIEVEMENTS, GRANTABLE, ONE_BY_ONE, PRIVATE, _grant, achievements,
    anthem_heard, answer_friend, ask_friend, find_student, link_card, add_by_link, friend_joined, friends, claim_qr,
    grant, grant_link, grant_scan, open_qr, qr_code, BADGE_OF, award_counts, award_people, awards_of,
    badge_sessions, my_links, revoke_link, undo_batch, person, seen_unlock, sync_levels, take_back,
    take_back_request, unfriend, ungrant, unlocked, use_grant_link)  # noqa: F401
from .organizing import (ALBUM_FOR, _asking, _norm_name, add_album_photo, attendee_ask, attendee_contact, attendees,
    attendees_export, can_add_album_photo, cancel_event, change_place, checkin, checkin_by_name, admin_delete_event,
    create_event, decline, delete_event, events_gone, delete_update, door, event_invites, invite_friend, kz_phone,
    leaders_answers, meeting_answers, org_events, post_update, publish_event, review_event, submit_event, rate_event,
    remove_album_photo, screen_came, staff_create_event, undo_checkin, update_event, set_reg_until, open_door,
    door_round)  # noqa: F401
from .organizing import DOC_BYTES, doc_check, drop_doc, put_doc, render_doc  # noqa: F401
from .daily import (_next_week, admin_ai, admin_day, admin_stats, ai_retry, day_of, memo, memo_again, memo_item,
    memo_opened, memo_sent, memo_sign, memo_week, saved_day, stats_day, tba_day, visit, wipe_hidden_posts)  # noqa: F401
from .teams import (accept_invite, banned, decide_removal, delete_role, delete_tag, invite, map_graph, map_rooms,
    members_export, president_link, remove, remove_member, save_role, save_tag, team, team_link, team_link_back, team_link_off,
    assign_role, team_setup, transfer, unban, update_member)  # noqa: F401
from .forum import (add_skill, ask_people, asks, block, close_ask, contact, contacts, create_ask, decide_contact,
    hide_ask, mod_hide_ask, mod_queue, my_forum, release_ask, reported_enough, search_people, set_my_forum, skill_mod,
    skills, telegram_of)  # noqa: F401
from .cohosts import co_runs  # noqa: F401
from . import ako, apple, appchats, appeals, assistant, autoev, chatmod, chatroles, chatsync, chattree, cohosts, crew, credits, evreports, evteams, fchannel, forms, gallery, helpus, inbox, library, mapflaws, pymk, research, rooms, santa, search, spy, stars, subjects, tgcomments, tournament, vol  # noqa: F401  (logic.fchannel.*: its names overlap the find-people forum's)
from ..db import tx  # noqa: F401  (callers take these from kbtu.logic)
