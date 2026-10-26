"""Settings from the environment: Coolify in production, ../.env in development. Secrets are never logged."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the repository: server/kbtu/config.py → KBTUapp/


@dataclass(frozen=True)
class Config:
    bot_token: str
    token_key: bytes            # the app's secret (32 bytes): signs the "To calendar" links
    db_path: str
    web_dist: str               # the built frontend
    domain: str = "kbtu.sow.kz"
    bot_username: str = "KBTUappBot"
    events_channel: str = ""    # where public events are posted (@KBTUevents on prod); empty: nowhere
    admins: frozenset[int] = frozenset()  # Telegram IDs that get the platform admin role
    old_dir: str | None = None  # the old prototype at /old/, kept for the pitch (dev: tmp-serve/)
    background: bool = True     # the postman and the schedule refresh (bot.py); tests turn them off
    cf_account_id: str = ""     # Cloudflare Workers AI translates event and club texts (ai.py); either empty: off
    cf_ai_token: str = ""
    forum: bool = False         # F1 find people: on for the app's staff only while it's tried out
    # the userbot (PLAN 86: an org's main channel into its news, userbot.py): an old Telegram account's StringSession
    # and the api pair it was made with (tools/userbot_login.py); any of the three empty: off, nothing else changes
    tg_api_id: str = ""
    tg_api_hash: str = field(default="", repr=False)
    tg_session: str = field(default="", repr=False)  # whoever has it is signed in as that account
    # the AI chain's other accounts (llm.py); any empty: its links are skipped
    munito_keys: tuple[str, ...] = field(default=(), repr=False)
    openrouter_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    ai_chain: str = ""          # "provider:model,..." over llm.CHAIN
    seed: bool = True           # KBTU's schools at start (logic.seed_schools); tests seed only where they look at them


def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    pairs = (line.strip().split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


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
        events_channel=env.get("EVENTS_CHANNEL", "@KBTUevents"),
        admins=frozenset(int(x) for x in env.get("ADMIN_TG_IDS", "").replace(",", " ").split()),
        old_dir=env.get("OLD_DIR") or None,
        background=env.get("BACKGROUND", "1") != "0",  # 0: no postman (tools/loadtest.py)
        cf_account_id=env.get("CF_ACCOUNT_ID", "").strip(),
        cf_ai_token=env.get("CF_AI_TOKEN", "").strip(),
        forum=env.get("FORUM", "0") == "1",
        tg_api_id=env.get("TG_API_ID", "").strip(),
        tg_api_hash=env.get("TG_API_HASH", "").strip(),
        tg_session=env.get("TG_SESSION", "").strip(),
        munito_keys=tuple(k for k in (env.get("MUNITO_API_KEY", "").strip(), env.get("MUNITO_API_KEY2", "").strip()) if k),
        openrouter_key=env.get("OPENROUTER_API_KEY", "").strip(),
        groq_key=env.get("GROQ_API_KEY", "").strip(),
        ai_chain=env.get("AI_CHAIN", "").strip(),
    )
