"""The rules of SPEC §2–§4 over SQLite, answering in the shapes of web/src/lib/api/types.ts (camelCase).

The only copy of the rules (the in-browser mock that repeated them went on Oct 11). Every function takes the connection and the caller (`Viewer`) and either returns
JSON-ready data or raises ApiError. Writes that check and then change (seats, check-in) run in db.tx.

Split by domain into the modules beside this file; everything is re-exported here, so callers
use kbtu.logic as before. A test that patches the clock or a limit patches the module that holds it (logic.core.now).
"""

from __future__ import annotations

from .core import (NAME, STUDENT_ID, ApiError, DOOR_AUTO, DOOR_EARLY, DOOR_LATE, door_at, door_shut, GOV_SLUG, HOLD, LEVEL_RIGHTS, NO_END, PERSON, PERSON_COLS,
    PROFILE_QR, RANK, RIGHTS, SEASON_MONTHS, TWO_GIS, Viewer, _by_id, _door_ref, _event_cover, _free_seat, _may, _once,
    _org, _qs, _rights, _rights_from, _roles, academic_year, add_photo, at_least, avatar_of, can, card, cards,
    clean_nick, course_cap, course_day, course_of, decided, free_taken, friend_ids, full, log, log_action, media_shape,
    need_student, now, one, org_ref, organizes, overseer, person_ref, photo, rights_of, role_in, rows, short_name,
    shown_name, taken)  # noqa: F401
from .seats import (ICS_KEY, _calendar, _chat_ok, _event, _fold, _hidden_orgs, _ics_text, _receipt_flags,
    _receipt_slot, _remind, _ticket_code, _vevent, _visible, _volunteers_view, add_receipt, add_seats, cal_feed,
    cal_token, reset_cal_token, channel_discussion, channel_due, channel_gone, chat_claim, chat_join, chat_start, end_of, event, guard_join, guard_read, guard_token,
    event_ics, events, ics_sig, notify, notify_staff, STAFF_KINDS, past_events, promote, receipt_open, receipt_path, register, review_receipt,
    joined, refill, signup_open, team_ask, team_asks, team_decide, team_guest, team_unask, set_saved, sweep_holds, title_in, unregister, volunteer_apply, volunteer_decide, volunteer_leave,
    volunteers_list)  # noqa: F401
from .queues import (AI_LIMIT, AI_LIMITS, AI_ORG_LIMITS, AI_POST_LIMITS, AI_POST_WAIT, AI_TRIES, _ai_note, _video,
    ai_failed, ai_next, ai_note, ai_save, ai_state, my_video, new_video, next_video, stale_videos, video_done,
    video_shape, video_uploaded)  # noqa: F401
from .account import (CONSENT, agreed, ai_on, policy, DELETE_WAIT, DELETION_LOG_DAYS, MS_KEEP, SETTINGS, SKINNED, LANYARDS, SCHOOL_LANYARDS, school_slug, _DEL_GONE,
    _DEL_KEEP, _deletion_log, _drop_photo, _drop_unused, _hand_over, _paid_ahead, _placeholder, _prune_deletion_log,
    _qr_code, _roster_mine, _skin, _skin_ok, _user_fks, ask_delete, consent, delete_due, delete_info, delete_me,
    deletion_hash, dm_on, drop_my_photo, drop_my_schedule, id_clash, keep_me, me, ms_apply, ms_check, ms_claim, ms_hold, ms_link, ms_pending, ms_remember, ms_sweep,
    FIXABLE, fix_identity, sid_tries, refer, roster_requests, save_schedule, schedule, set_photo, update_me)  # noqa: F401
from .clubs import (CLUB_REAPPLY, COVERS, KBTU, LINK, LINKS_MAX, LINK_WORDS, OFFICIAL_ROLES, REAPPLY, RESERVED,
    SCHOOLS, SCHOOLS_VERSION, SHORT, SLUG, TRANSLIT, _HEAD, _KB, _SEP, _TAIL, _acronym, _club_app, _keep_name,
    _links_ok, _my_request, _official, _people, _request_state, _slug_free, add_link, apply, apply_club,
    club_applications, create_org, decide_club_application, delete_org, PATH_STEPS, path_top, ask_official, decide_official, official_path, official_requests, undo_official, undo_club_refusal, decide_join, drop_link, fill_abbrs, guess_abbr, initials,
    join_requests, my_club_application, name_slugs, org, org_by_slug, org_links, org_name, org_shape, org_shapes, orgs,
    listed, people, seed_schools, shown_links, slug_for, start_by_slug, strip_emoji_names, no_emoji, subscribe, update_org, withdraw)  # noqa: F401
from .newsfeed import (POST_TAGS, _tg_i18n, _tg_shape, cancel_casting, casting_state, castings, create_post, feature, hide_post, post_shape, post_shapes, posts,
    react, read_posts, unread_broadcasts, update_post, wipe_post)  # noqa: F401
from .chatlist import (HANDLE, INVITE, ORG_CHATS, SAME_CHAT, TG_LINK, _chat, _chats_audit, _closed, _owned, _unlink,
    add_chat, add_org_chat, approve_chat, bot_added, bot_admin, bot_unwait, my_waits, wait_target, claim_wait, chat_held, tag_all, chat_pick, pick_claim, bot_left, chat_card, chat_handle, chat_input, chat_link,
    chat_opened, chat_refreshed, chats, chats_gone, delete_chat, pending_chats, undo_chat, drop_org_chat, main_org_chat, may_chats,
    mirror_org_chat, org_chats, photo_free, set_chat_org, suggest_chat, suggest_check, SECTIONS, chat_links, known_chat,
    set_chat_section, sort_next, sort_save, chat_asked_too)  # noqa: F401
from .oversight import (DMP_COLS, QUIET_FOR, STAFF_ROLES, _STAFF, _admin, _admin_org, _dmp_person, _mod, _month,
    _overseer_only, _owner, _staff_row, _touchable, admin_create_org, admin_hide_org, admin_org_events, admin_orgs,
    admin_set_role, audit, ban_info, find_people, find_user, registry, registry_export, registry_memos,
    registry_roster, registry_search, set_ban, set_official, set_role, set_staff, set_staff_mute, staff, staff_mutes)  # noqa: F401
from .moderation import (COMMENTS_A_MINUTE, REPORTS_A_DAY, REPORT_NOTE, TAKEDOWN_KEEP, _about, _moderates, _thread,
    add_comment, close_gone, comments, delete_comment, purge_takedowns, report, report_queue, resolve_report, restore,
    set_comments_on)  # noqa: F401
from .profiles import (ACHIEVEMENTS, FIRST_N, FRIEND_ASKS_A_DAY, GRANTABLE, CREATOR_ONLY, ONE_BY_ONE, PRIVATE, PROFILES_A_DAY,
    REASK_AFTER, _befriend, _came, _celebrate, _counts, _drop_grant, _friend_row, _grant, _levels, _season_start,
    _stranger_view, _streak, _student, _week, achievements, anthem_heard, answer_friend, ask_friend, attended, brought, card_no,
    find_student, first_fifty, link_card, add_by_link, friend_joined, friends, friendship, claim_link, claim_qr, grant, grant_link, grant_scan, open_qr, qr_code,
    BADGES, BADGE_OF, award_counts, award_people, awards_of, badge_sessions, my_links, revoke_link, undo_batch, person, seen_unlock, sync_levels, take_back, take_back_request, unfriend, ungrant, unlocked,
    use_grant_link)  # noqa: F401
from .organizing import (ALBUM_EACH, ALBUM_FOR, ALBUM_MAX, ALBUM_TEAM, GUEST_DAYS,
    INVITES_A_DAY, LEAD_ROLES, PHOTO_REPORT_AT, RATE_FOR, RATE_SHOW, SLIDES, UNDO, UPDATES_A_DAY, _album_room,
    _album_view, _ask_rating, _asking, _changed, _cover, _expected, _focus, _invited_leaders, _meeting_ok,
    _norm_name, _pay, _rating_view, _slides, _staff_event, _team_door, _walk_in, add_album_photo,
    attendees, attendees_export, can_add_album_photo, cancel_event, change_place, checkin, checkin_by_name,
    admin_delete_event, clean_event, create_event, decline, delete_event, events_gone, undo_delete_event, delete_update, door, event_invites, invite_friend,
    kz_phone, leaders_answers, link_door_guests, meeting_answers, org_events, post_update, publish_event, rate_event,
    remove_album_photo, screen_came, shade, staff_create_event, undo_checkin, update_event, set_reg_until, open_door, door_round)  # noqa: F401
from .daily import (MEMO_ASKS, _AI_EVENTS, _AI_ORGS, _memo, _memo_sender, _next_week, _room_no, admin_ai, admin_day,
    admin_stats, ai_retry, day_of, memo, memo_again, memo_item, memo_opened, memo_sent, memo_sign, memo_week,
    saved_day, stats_day, tba_day, visit, wipe_hidden_posts)  # noqa: F401
from .teams import (HEX, INVITE_TTL, MAP_DRAFT, PRESIDENT_LINK_TTL, normalize_role, roles_backfill, _ask_removal, _below, _manage, _named, _ordered,
    _remove, accept_invite, banned, decide_removal, delete_role, delete_tag, depts_of, invite, map_graph, map_rooms,
    TEAM_LINK_TTL, members_export, president_link, remove, remove_member, save_role, save_tag, team, team_link, team_link_off, assign_role, team_setup, transfer, unban, update_member, set_dept)  # noqa: F401
from .forum import (ASK_SKILLS, BODY_MAX, CONTACTS_A_DAY, DAYS, DECIDE_IN, HIDE_AT, KEEP, MY_SKILLS, NAME_MAX,
    NEW_SKILLS_A_DAY, OPEN_ASKS, PING_DAY, PING_TOP, PING_WEEK, PUBLIC_AT, REPORTER_AGE, SEARCHES_AN_HOUR, STALE,
    TITLE_MAX, _FINDABLE, _UNBLOCKED, _ask_shape, _card, _enough_at, _holders, _matches, _now, _ping, _skill,
    _skills_of, add_skill, ask_people, asks, block, close_ask, contact, contacts, create_ask, decide_contact,
    forum_sweep, hide_ask, mod_hide_ask, mod_queue, my_forum, norm_skill, release_ask, reported_enough, search_people,
    set_my_forum, skill_lookup, skill_mod, skills, telegram_of)  # noqa: F401
from .cohosts import co_runs  # noqa: F401
from . import appeals, assistant, chatmod, chatroles, chatsync, cohosts, crew, evreports, evteams, fchannel, gallery, inbox, mapflaws, search, stars, tgcomments, vol  # noqa: F401  (logic.fchannel.*: its names overlap the find-people forum's)
from ..db import tx  # noqa: F401  (callers took these from the old module)
