"""Settings from the environment: Coolify in production, ../.env in development. Secrets are never logged."""
from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .auth import BOT_TOKEN

ROOT = Path(__file__).resolve().parents[2]  # the repository: server/kbtu/config.py → KBTUapp/


@dataclass(frozen=True)
class Config:
    bot_token: str = field(repr=False)
    token_key: bytes = field(repr=False)  # the app's secret (32 bytes): signs the "To calendar" links
    db_path: str
    web_dist: str               # the built frontend
    domain: str = "kbtu.sow.kz"
    bot_username: str = "KBTUappBot"
    events_channel: str = ""    # where public events are posted (@KBTUevents on prod); empty: nowhere
    admins: frozenset[int] = frozenset()  # Telegram IDs that get the platform admin role
    old_dir: str | None = None  # Serve /old/ for the pitch when its files are configured.
    background: bool = True     # the postman and the schedule refresh (bot.py); tests turn them off
    cf_account_id: str = ""     # Cloudflare Workers AI translates event and club texts (ai.py); either empty: off
    cf_ai_token: str = field(default="", repr=False)
    forum: bool = False         # F1 find people: on for the app's staff only while it's tried out
    forum_founder: bool = False  # FORUM=founder: the Creator alone, before the staff
    # the policy's section 12 (the assistant, sign-up questions, the map's flaws): BOARD=1 every student,
    # BOARD=staff the app's staff only to try it
    board: str = ""
    # the forum channel's discussion group (its chat id, -100...): only verified students may comment there (tgc.py,
    # logic/tgcomments.py); 0: all of it off. Never the events
    # channel's discussion group: the bot would take its post copies as this group's and never comment under them
    tgc_chat: int = 0
    # the forum channel itself (@KBTUappForum's chat id, -100...): students post from the app, the bot publishes after
    # the AI's or a moderator's yes (logic/fchannel.py); 0: off
    forum_channel: int = 0
    # MS_AGE_CUTOFF=MM-DD (e.g. 06-01): free 1st-year seats only for a Microsoft account made on or after that day of
    # the academic year's first calendar year (logic/core.py first_year_free); empty: the date is only recorded
    ms_age_cutoff: str = ""
    # The userbot (userbot.py) mirrors an org's main channel into its news. It needs a StringSession
    # and the api pair it was made with (tools/userbot_login.py); any of the three empty: off, nothing else changes
    tg_api_id: str = ""
    tg_api_hash: str = field(default="", repr=False)
    tg_session: str = field(default="", repr=False)  # whoever has it is signed in as that account
    # the AI chain's other accounts (llm.py); any empty: its links are skipped
    munito_keys: tuple[str, ...] = field(default=(), repr=False)
    openrouter_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    apinex_key: str = field(default="", repr=False)  # APINEX_API_KEY: the chain's first link
    gemini_key: str = field(default="", repr=False)  # GEMINI_API_KEY: Google (llm.GOOGLE)
    assist_lead: str = ""       # ASSIST_LEAD: unset or google, Google answers first for who said yes (assistant.GOOGLE_YES); off: never
    ai_chain: str = ""          # "provider:model,..." over llm.CHAIN
    # DONATE_PHONE: the creator's Kaspi number for "Support the app" (Settings); empty: Stars only.
    # Never in the repo, the bundle or the logs (repr=False)
    donate_phone: str = field(default="", repr=False)
    # The name + initial printed by Kaspi for that phone's owner. Empty: every donation needs the creator's review.
    donate_recipient: str = field(default="", repr=False)
    # VOLUNTEERS=<club slug>: that club's volunteers ledger (logic/vol.py); empty: off
    volunteers: str = ""
    # APPEALS=1: appeals to the Student Government for everyone (logic/appeals.py); staff: admins, moderators and SG's people
    appeals: str = ""
    # ASK=1: KRI's "Ask a person", the help desk of appeals for everyone (logic/appeals.py); staff: admins, moderators and its people
    ask: str = ""
    # GALLERY=1: everyone posts to the Gallery (logic/gallery.py: KBTU's own photos beside the albums); staff: admins and moderators
    gallery: str = ""
    # CHAT_SYNC=1: clubs' members mirrored from their linked Telegram chats (logic/chatsync.py); off: none of it runs
    chat_sync: bool = False
    # DOCS=1: the assistant answers from the university's documents too (kbtu/docs.py, a separate file at DOCS_DB, next
    # to the database by default); DOCS=hybrid: and the question's own embedding from Cloudflare, only where the policy
    # names Cloudflare for the assistant's questions (app.py); empty: off
    docs: str = ""
    docs_db: str = ""
    # TIKTOK=1: answer supported group links with the video (tiktok.py). INSTAGRAM_COOKIES (Instagram stories) is
    # deliberately not here: tiktok.py reads it from the environment at each call, so its path is in no Config, no repr
    tiktok: bool = False
    # IG_USER_ID + IG_TOKEN: the app's own Instagram professional account and its long-lived token; the clubs' Instagram
    # posts come into their news through Business Discovery (instagram.py, README "Clubs' Instagram posts"); either empty: off
    ig_user_id: str = ""
    ig_token: str = field(default="", repr=False)
    # REPORTS=1: clubs' event reports and personal attendance logs (logic/evreports.py, privacy policy section 3)
    reports: bool = False
    # ROOMS_FILE: the map's "free now", the timetable's busy rooms (tools/rooms.py), next to the database by default; no file: off
    rooms_file: str = ""
    # SUBJECTS_FILE: the subjects' cards (tools/subjects.py: names, codes, credits, school only), next to the database by default; no file: off
    subjects_file: str = ""
    # IOS_BUNDLE_ID: the iPhone app's bundle ID (kz.sow.kbtu, ios/README.md), the audience its Apple identity tokens
    # must name; empty: Sign in with Apple and iPhone push are off. APNS_KEY_ID, APNS_TEAM_ID, APNS_KEY (the .p8's text, \n allowed): push
    # through Apple (apns.py); any empty: no push, the bot alone
    ios_bundle: str = ""
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_key: str = field(default="", repr=False)
    seed: bool = True         # KBTU's schools at start (logic.seed_schools); tests seed only where they look at them
    # PLAY_DEMO: Google Play's reviewer signs in at /play-demo?k=<this> (logic/web_auth.py, android/README.md); empty: off,
    # and every demo session with it. 32+ random characters, or off
    play_demo: str = field(default="", repr=False)
    # ANDROID_CERT_SHA256: the Android app's signing certificates (AA:BB:..., comma-separated) for
    # /.well-known/assetlinks.json; empty: no file, the app shows a browser bar
    android_certs: tuple[str, ...] = ()
    # Apple Wallet (wallet.py): the Pass Type ID certificate followed by Apple's WWDR intermediate (PEM), its key, the
    # pass type ID and the team ID; any empty: off (no button, the route is a 404)
    wallet_cert: str = field(default="", repr=False)
    wallet_key: str = field(default="", repr=False)
    wallet_type_id: str = ""
    apple_team_id: str = ""


def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    pairs = (line.strip().split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def _month_day(s: str) -> str:
    """MS_AGE_CUTOFF: empty, or a real MM-DD (a typo would silently refuse or let in everyone's free seat)"""
    try:
        ok = not s or len(s) == 5 and bool(time.strptime("2024-" + s, "%Y-%m-%d"))  # a leap year: 02-29 is a day
    except ValueError:
        ok = False
    if not ok:
        raise SystemExit("MS_AGE_CUTOFF must be MM-DD, e.g. 06-01")
    return s


def _kz_phone(s: str) -> str:
    """DONATE_PHONE: empty, or a Kazakh number as +7XXXXXXXXXX (a typo would send students' money to a stranger)"""
    d = "".join(c for c in s if c.isdigit())
    d = "7" + d[1:] if len(d) == 11 and d[0] == "8" else d
    if s and not (len(d) == 11 and d[0] == "7"):  # off, not a crash: a typo in the env mustn't take the app down
        print("DONATE_PHONE is not a Kazakh number (+7 700 000 00 00): the Support page is off", flush=True)
        return ""
    return "+" + d if s else ""


def _play_demo(s: str) -> str:
    """PLAY_DEMO: the reviewer's link is the only key to the demo account; a short one could be guessed"""
    if s and len(s) < 32:
        print("PLAY_DEMO is shorter than 32 characters: the Play review demo is off", flush=True)
        return ""
    return s


def _certs(s: str) -> tuple[str, ...]:
    """ANDROID_CERT_SHA256: SHA-256 fingerprints as AA:BB:... (Play Console's app signing page, keytool -list)"""
    certs = tuple(x.strip().upper() for x in s.split(",") if x.strip())
    if bad := [x for x in certs if not re.fullmatch(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}", x)]:
        print(f"ANDROID_CERT_SHA256: {len(bad)} entries aren't SHA-256 fingerprints (AA:BB:...): left out", flush=True)
    return tuple(x for x in certs if x not in bad)


def load() -> Config:
    env = {**_dotenv(), **os.environ}
    key = base64.b64decode(env["TOKEN_KEY"]) if env.get("TOKEN_KEY") else b""
    if len(key) != 32:
        raise SystemExit("TOKEN_KEY must be 32 random bytes in base64 (python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')")
    token = env.get("BOT_TOKEN", "")
    if not BOT_TOKEN.fullmatch(token):
        raise SystemExit("BOT_TOKEN must be a Telegram bot token from BotFather")
    db_path = env.get("DB_PATH", str(ROOT / "server" / "kbtu.db"))
    # the image sets DB_MUST_EXIST=1: production data lives in an encrypted vault (DEPLOY.md), and a vault that didn't
    # open leaves an empty folder; a fresh database there would look like a working app with nobody in it
    if env.get("DB_MUST_EXIST") == "1" and not Path(db_path).is_file():
        raise SystemExit(f"{db_path} is missing (vault locked?). A brand-new install sets DB_MUST_EXIST=0 once")
    return Config(
        bot_token=token,
        token_key=key,
        db_path=db_path,
        web_dist=env.get("WEB_DIST", str(ROOT / "web" / "dist")),
        domain=env.get("DOMAIN", "kbtu.sow.kz"),
        bot_username=env.get("BOT_USERNAME", "KBTUappBot"),
        events_channel=env.get("NEWS_CHANNEL") or env.get("EVENTS_CHANNEL") or "@KBTUevents",  # Accept EVENTS_CHANNEL so existing deployments can keep their configuration.
        admins=frozenset(int(x) for x in env.get("ADMIN_TG_IDS", "").replace(",", " ").split()),
        old_dir=env.get("OLD_DIR") or None,
        background=env.get("BACKGROUND", "1") != "0",  # 0: no postman (tools/loadtest.py)
        cf_account_id=env.get("CF_ACCOUNT_ID", "").strip(),
        cf_ai_token=env.get("CF_AI_TOKEN", "").strip(),
        forum=env.get("FORUM", "0") == "1",
        forum_founder=env.get("FORUM", "0") == "founder",
        board={"1": "all", "staff": "staff"}.get(env.get("BOARD", "").strip(), ""),
        tgc_chat=int((env.get("FORUM_GROUP") or env.get("TG_COMMENTS_CHAT") or "").strip() or 0),  # Accept TG_COMMENTS_CHAT so existing deployments can keep their configuration.
        forum_channel=int(env.get("FORUM_CHANNEL", "").strip() or 0),
        ms_age_cutoff=_month_day(env.get("MS_AGE_CUTOFF", "").strip()),
        tg_api_id=env.get("TG_API_ID", "").strip(),
        tg_api_hash=env.get("TG_API_HASH", "").strip(),
        tg_session=env.get("TG_SESSION", "").strip(),
        munito_keys=tuple(k for k in (env.get(f"MUNITO_API_KEY{n}", "").strip() for n in ("", *map(str, range(2, 10)))) if k),  # KEY, KEY2..KEY9
        openrouter_key=env.get("OPENROUTER_API_KEY", "").strip(),
        groq_key=env.get("GROQ_API_KEY", "").strip(),
        apinex_key=env.get("APINEX_API_KEY", "").strip(),
        gemini_key=env.get("GEMINI_API_KEY", "").strip(),
        assist_lead=env.get("ASSIST_LEAD", "").strip().lower(),
        ai_chain=env.get("AI_CHAIN", "").strip(),
        donate_phone=_kz_phone(env.get("DONATE_PHONE", "").strip()),
        donate_recipient=env.get("DONATE_RECIPIENT", "").strip()[:120],
        volunteers=env.get("VOLUNTEERS", "").strip().lower(),
        appeals={"1": "all", "staff": "staff"}.get(env.get("APPEALS", "").strip(), ""),
        ask={"1": "all", "staff": "staff"}.get(env.get("ASK", "").strip(), ""),
        gallery={"1": "all", "staff": "staff"}.get(env.get("GALLERY", "").strip(), ""),
        chat_sync=env.get("CHAT_SYNC", "").strip() == "1",
        docs={"1": "fts", "hybrid": "hybrid"}.get(env.get("DOCS", "").strip(), ""),
        docs_db=env.get("DOCS_DB") or str(Path(db_path).parent / "docs.db"),
        reports=env.get("REPORTS", "").strip() == "1",
        tiktok=env.get("TIKTOK", "").strip() == "1",
        ig_user_id=uid if (uid := env.get("IG_USER_ID", "").strip()).isdigit() else "",  # a typo: off, never a call with it
        ig_token=env.get("IG_TOKEN", "").strip(),
        rooms_file=env.get("ROOMS_FILE") or str(Path(db_path).parent / "rooms.json"),
        subjects_file=env.get("SUBJECTS_FILE") or str(Path(db_path).parent / "subjects.json"),
        ios_bundle=env.get("IOS_BUNDLE_ID", "").strip(),
        apns_key_id=env.get("APNS_KEY_ID", "").strip(),
        apns_team_id=env.get("APNS_TEAM_ID", "").strip(),
        apns_key=env.get("APNS_KEY", "").strip().replace("\\n", "\n"),
        play_demo=_play_demo(env.get("PLAY_DEMO", "").strip()),
        android_certs=_certs(env.get("ANDROID_CERT_SHA256", "")),
        wallet_cert=env.get("WALLET_PASS_CERT", "").strip(),
        wallet_key=env.get("WALLET_PASS_KEY", "").strip(),
        wallet_type_id=env.get("WALLET_PASS_TYPE_ID", "").strip(),
        apple_team_id=env.get("APPLE_TEAM_ID", "").strip(),
    )
