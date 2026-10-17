"""Settings from the environment: Coolify in production, ../.env in development. Secrets are never logged."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
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
    return Config(
        bot_token=env["BOT_TOKEN"],
        token_key=key,
        db_path=env.get("DB_PATH", str(ROOT / "server" / "kbtu.db")),
        web_dist=env.get("WEB_DIST", str(ROOT / "web" / "dist")),
        domain=env.get("DOMAIN", "kbtu.sow.kz"),
        bot_username=env.get("BOT_USERNAME", "KBTUappBot"),
        events_channel=env.get("EVENTS_CHANNEL", "@KBTUevents"),
        admins=frozenset(int(x) for x in env.get("ADMIN_TG_IDS", "").replace(",", " ").split()),
        old_dir=env.get("OLD_DIR") or None,
        background=env.get("BACKGROUND", "1") != "0",  # 0: no postman (tools/loadtest.py)
    )
