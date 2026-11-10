"""Settings from the environment: Coolify in production, ../.env in development. Secrets are never logged."""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

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
    old_dir: str | None = None  # the old prototype at /old/, kept for the pitch (dev: tmp-serve/)
    background: bool = True     # the postman and the schedule refresh (bot.py); tests turn them off
    cf_account_id: str = ""     # Cloudflare Workers AI translates event and club texts (ai.py); either empty: off
    cf_ai_token: str = field(default="", repr=False)
    forum: bool = False         # F1 find people: on for the app's staff only while it's tried out
    forum_founder: bool = False  # FORUM=founder: the Creator alone, before the staff
    # the policy's section 12 (the assistant, sign-up questions, the map's flaws): BOARD=1 every student (in force,
    # everyone agrees again), BOARD=staff the app's staff only to try it (no new policy version: nobody else is asked anything)
    board: str = ""
    # the forum channel's discussion group (its chat id, -100...): only verified students may comment there (tgc.py,
    # logic/tgcomments.py); 0: all of it off, the policy's section and its consent version too. Never the events
    # channel's discussion group: the bot would take its post copies as this group's and never comment under them
    tgc_chat: int = 0
    # the forum channel itself (@KBTUappForum's chat id, -100...): students post from the app, the bot publishes after
    # the AI's or a moderator's yes (logic/fchannel.py); 0: off, the policy's section and its consent version too
    forum_channel: int = 0
    # MS_AGE_CUTOFF=MM-DD (e.g. 06-01): free 1st-year seats only for a Microsoft account made on or after that day of
    # the academic year's first calendar year (logic/core.py first_year_free); empty: the date is only recorded
    ms_age_cutoff: str = ""
    # the userbot (PLAN 86: an org's main channel into its news, userbot.py): an old Telegram account's StringSession
    # and the api pair it was made with (tools/userbot_login.py); any of the three empty: off, nothing else changes
    tg_api_id: str = ""
    tg_api_hash: str = field(default="", repr=False)
    tg_session: str = field(default="", repr=False)  # whoever has it is signed in as that account
    # the AI chain's other accounts (llm.py); any empty: its links are skipped
    munito_keys: tuple[str, ...] = field(default=(), repr=False)
    openrouter_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    apinex_key: str = field(default="", repr=False)  # APINEX_API_KEY: the chain's first link
    ai_chain: str = ""          # "provider:model,..." over llm.CHAIN
    # DONATE_PHONE: the creator's Kaspi number for the voluntary "Support the app" page (Settings); empty: no row.
    # Never in the repo, the bundle or the logs (repr=False); .claude/reports/donate-review.md
    donate_phone: str = field(default="", repr=False)
    # VOLUNTEERS=<club slug>: that club's volunteers ledger (logic/vol.py) and its privacy section; empty: off
    volunteers: str = ""
    # APPEALS=1: appeals to the Student Government for everyone (logic/appeals.py); staff: admins, moderators and SG's people
    appeals: str = ""
    # GALLERY=1: everyone posts to the Gallery (logic/gallery.py: KBTU's own photos beside the albums); staff: admins and moderators
    gallery: str = ""
    # CHAT_SYNC=1: clubs' members mirrored from their linked Telegram chats (logic/chatsync.py) and its privacy section; off: none of it runs
    chat_sync: bool = False
    # DOCS=1: the assistant answers from the university's documents too (kbtu/docs.py, a separate file at DOCS_DB, next
    # to the database by default); DOCS=hybrid: and the question's own embedding from Cloudflare, only where the policy
    # names Cloudflare for the assistant's questions (app.py); empty: off
    docs: str = ""
    docs_db: str = ""
    seed: bool = True         # KBTU's schools at start (logic.seed_schools); tests seed only where they look at them


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


def load() -> Config:
    env = {**_dotenv(), **os.environ}
    key = base64.b64decode(env["TOKEN_KEY"]) if env.get("TOKEN_KEY") else b""
    if len(key) != 32:
        raise SystemExit("TOKEN_KEY must be 32 random bytes in base64 (python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())')")
    db_path = env.get("DB_PATH", str(ROOT / "server" / "kbtu.db"))
    # the image sets DB_MUST_EXIST=1: production data lives in an encrypted vault (DEPLOY.md), and a vault that didn't
    # open leaves an empty folder; a fresh database there would look like a working app with nobody in it
    if env.get("DB_MUST_EXIST") == "1" and not Path(db_path).is_file():
        raise SystemExit(f"{db_path} is missing (vault locked?). A brand-new install sets DB_MUST_EXIST=0 once")
    return Config(
        bot_token=env["BOT_TOKEN"],
        token_key=key,
        db_path=db_path,
        web_dist=env.get("WEB_DIST", str(ROOT / "web" / "dist")),
        domain=env.get("DOMAIN", "kbtu.sow.kz"),
        bot_username=env.get("BOT_USERNAME", "KBTUappBot"),
        events_channel=env.get("NEWS_CHANNEL") or env.get("EVENTS_CHANNEL") or "@KBTUevents",  # the old name still works
        admins=frozenset(int(x) for x in env.get("ADMIN_TG_IDS", "").replace(",", " ").split()),
        old_dir=env.get("OLD_DIR") or None,
        background=env.get("BACKGROUND", "1") != "0",  # 0: no postman (tools/loadtest.py)
        cf_account_id=env.get("CF_ACCOUNT_ID", "").strip(),
        cf_ai_token=env.get("CF_AI_TOKEN", "").strip(),
        forum=env.get("FORUM", "0") == "1",
        forum_founder=env.get("FORUM", "0") == "founder",
        board={"1": "all", "staff": "staff"}.get(env.get("BOARD", "").strip(), ""),
        tgc_chat=int((env.get("FORUM_GROUP") or env.get("TG_COMMENTS_CHAT") or "").strip() or 0),  # the old name still works
        forum_channel=int(env.get("FORUM_CHANNEL", "").strip() or 0),
        ms_age_cutoff=_month_day(env.get("MS_AGE_CUTOFF", "").strip()),
        tg_api_id=env.get("TG_API_ID", "").strip(),
        tg_api_hash=env.get("TG_API_HASH", "").strip(),
        tg_session=env.get("TG_SESSION", "").strip(),
        munito_keys=tuple(k for k in (env.get(f"MUNITO_API_KEY{n}", "").strip() for n in ("", *map(str, range(2, 10)))) if k),  # KEY, KEY2..KEY9
        openrouter_key=env.get("OPENROUTER_API_KEY", "").strip(),
        groq_key=env.get("GROQ_API_KEY", "").strip(),
        apinex_key=env.get("APINEX_API_KEY", "").strip(),
        ai_chain=env.get("AI_CHAIN", "").strip(),
        donate_phone=_kz_phone(env.get("DONATE_PHONE", "").strip()),
        volunteers=env.get("VOLUNTEERS", "").strip().lower(),
        appeals={"1": "all", "staff": "staff"}.get(env.get("APPEALS", "").strip(), ""),
        gallery={"1": "all", "staff": "staff"}.get(env.get("GALLERY", "").strip(), ""),
        chat_sync=env.get("CHAT_SYNC", "").strip() == "1",
        docs={"1": "fts", "hybrid": "hybrid"}.get(env.get("DOCS", "").strip(), ""),
        docs_db=env.get("DOCS_DB") or str(Path(db_path).parent / "docs.db"),
    )
