"""The rules of SPEC §2–§4 over SQLite, answering in the shapes of web/src/lib/api/types.ts (camelCase).

The only copy of the rules (the in-browser mock that repeated them went on Oct 11). Every function takes the connection and the caller (`Viewer`) and either returns
JSON-ready data or raises ApiError. Writes that check and then change (seats, check-in) run in db.tx.

Split by domain into the modules beside this file; everything is re-exported here, so callers
use kbtu.logic as before. A test that patches the clock or a limit patches the module that holds it (logic.core.now).
"""

from __future__ import annotations

from .core import (ApiError, DOOR_EARLY, DOOR_LATE, GOV_SLUG, HOLD, LEVEL_RIGHTS, NO_END, PERSON, PERSON_COLS,
    PROFILE_QR, RANK, RIGHTS, SEASON_MONTHS, TWO_GIS, Viewer, _by_id, _door_ref, _event_cover, _free_seat, _may, _once,
    _org, _qs, _rights, _rights_from, _roles, academic_year, add_photo, at_least, avatar_of, can, card, cards,
    clean_nick, course_cap, course_day, course_of, free_taken, friend_ids, full, log, log_action, media_shape,
    need_student, now, one, org_ref, organizes, overseer, person_ref, photo, rights_of, role_in, rows, short_name,
    shown_name, taken)  # noqa: F401
from .seats import (ICS_KEY, _calendar, _chat_ok, _event, _fold, _ics_text, _receipt_flags, _receipt_slot, _remind,
    _ticket_code, _vevent, _visible, _volunteers_view, add_receipt, add_seats, cal_feed, cal_token, channel_discussion,
    channel_due, channel_gone, chat_claim, chat_join, chat_start, end_of, event, event_ics, events, ics_sig, notify,
    past_events, promote, receipt_open, receipt_path, register, review_receipt, set_saved, sweep_holds, tickets,
    title_in, unregister, volunteer_apply, volunteer_decide, volunteer_leave, volunteers_list)  # noqa: F401
from .queues import (AI_LIMIT, AI_LIMITS, AI_ORG_LIMITS, AI_POST_LIMITS, AI_POST_WAIT, AI_TRIES, _ai_note, _video,
    ai_failed, ai_next, ai_note, ai_save, ai_state, my_video, new_video, next_video, stale_videos, video_done,
    video_shape, video_uploaded)  # noqa: F401
from .account import (CONSENT, DELETE_WAIT, DELETION_LOG_DAYS, MS_KEEP, SETTINGS, SKINNED, _DEL_GONE, _DEL_KEEP,
    _deletion_log, _drop_photo, _drop_unused, _hand_over, _paid_ahead, _placeholder, _prune_deletion_log, _qr_code,
    _roster_mine, _skin, _skin_ok, _user_fks, ask_delete, consent, delete_due, delete_info, delete_me, deletion_hash,
    dm_on, drop_my_photo, id_clash, keep_me, me, ms_apply, ms_link, ms_pending, ms_remember, ms_sweep, roster_requests,
    save_schedule, schedule, set_photo, update_me)  # noqa: F401
from .clubs import (CLUB_REAPPLY, COVERS, KBTU, LINK, LINKS_MAX, LINK_WORDS, OFFICIAL_ROLES, REAPPLY, RESERVED,
    SCHOOLS, SCHOOLS_VERSION, SHORT, SLUG, TRANSLIT, _HEAD, _KB, _SEP, _TAIL, _acronym, _club_app, _keep_name,
    _links_ok, _my_request, _official, _people, _request_state, _slug_free, add_link, apply, apply_club,
    club_applications, create_org, decide_club_application, decide_join, drop_link, fill_abbrs, guess_abbr, initials,
    join_requests, my_club_application, name_slugs, org, org_by_slug, org_links, org_name, org_shape, org_shapes, orgs,
    people, seed_schools, slug_for, start_by_slug, subscribe, update_org, withdraw)  # noqa: F401
from .newsfeed import (POST_TAGS, _tg_i18n, _tg_shape, create_post, feature, hide_post, post_shape, post_shapes, posts,
    react, read_posts, unread_broadcasts, update_post)  # noqa: F401
from .chatlist import (HANDLE, INVITE, ORG_CHATS, SAME_CHAT, TG_LINK, _chat, _chats_audit, _closed, _owned, _unlink,
    add_chat, add_org_chat, approve_chat, bot_added, bot_left, chat_card, chat_handle, chat_input, chat_link,
    chat_opened, chat_orgs, chat_refreshed, chats, delete_chat, drop_org_chat, main_org_chat, may_chats,
    mirror_org_chat, org_chats, photo_free, set_chat_org, suggest_chat, suggest_check)  # noqa: F401
from .oversight import (DMP_COLS, QUIET_FOR, STAFF_ROLES, _STAFF, _admin, _admin_org, _dmp_person, _mod, _month,
    _overseer_only, _owner, _staff_row, _touchable, admin_create_org, admin_hide_org, admin_org_events, admin_orgs,
    admin_set_role, audit, ban_info, find_anyone, find_user, registry, registry_export, registry_memos,
    registry_roster, registry_search, set_ban, set_official, set_role, set_staff, staff)  # noqa: F401
from .moderation import (COMMENTS_A_MINUTE, REPORTS_A_DAY, REPORT_NOTE, TAKEDOWN_KEEP, _about, _moderates, _thread,
    add_comment, comments, delete_comment, purge_takedowns, report, report_queue, resolve_report, restore,
    set_comments_on, taken_down)  # noqa: F401
from .profiles import (ACHIEVEMENTS, FIRST_N, FRIEND_ASKS_A_DAY, GRANTABLE, GRANT_LINK_TTL, LINK_TTL, PROFILES_A_DAY,
    REASK_AFTER, _befriend, _came, _celebrate, _counts, _drop_grant, _friend_row, _grant, _levels, _season_start,
    _stranger_view, _streak, _student, _week, achievements, answer_friend, ask_friend, attended, card_no, find_student,
    first_fifty, friend_link, friend_link_used, friends, friendship, grant, grant_link, grant_scan, my_grants, person,
    seen_unlock, sync_levels, take_back, take_back_request, unfriend, ungrant, unlocked, use_friend_link,
    use_grant_link)  # noqa: F401
from .organizing import (ALBUM_EACH, ALBUM_FOR, ALBUM_MAX, ALBUM_TEAM, GUESTS_MAX, GUEST_DAYS, GUEST_NAME,
    INVITES_A_DAY, LEAD_ROLES, PHOTO_REPORT_AT, RATE_FOR, RATE_SHOW, SLIDES, UNDO, UPDATES_A_DAY, _album_room,
    _album_view, _ask_rating, _asking, _changed, _cover, _expected, _focus, _guest, _invited_leaders, _meeting_ok,
    _norm_name, _pay, _rating_view, _slides, _staff_event, _team_door, _walk_in, add_album_photo, add_door_guest,
    attendees, attendees_export, can_add_album_photo, cancel_event, change_place, checkin, checkin_by_name,
    clean_event, create_event, decline, delete_event, delete_update, door, door_guests, event_invites, invite_friend,
    kz_phone, leaders_answers, link_door_guests, meeting_answers, org_events, post_update, publish_event, rate_event,
    remove_album_photo, shade, undo_checkin, undo_door_guest, update_event)  # noqa: F401
from .daily import (MEMO_ASKS, _AI_EVENTS, _AI_ORGS, _memo, _memo_sender, _next_week, _room_no, admin_ai, admin_day,
    admin_stats, ai_retry, day_of, memo, memo_again, memo_item, memo_opened, memo_sent, memo_sign, memo_week,
    saved_day, stats_day, tba_day, visit)  # noqa: F401
from .teams import (HEX, INVITE_TTL, MAP_DRAFT, PRESIDENT_LINK_TTL, _ask_removal, _below, _manage, _named, _ordered,
    _remove, accept_invite, banned, decide_removal, delete_role, delete_tag, dept_of, invite, map_graph,
    president_link, remove, remove_member, save_role, save_tag, team, team_setup, transfer, unban, update_member)  # noqa: F401
from ..db import tx  # noqa: F401  (callers took these from the old module)
