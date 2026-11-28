"""Admissions reminders out (logic/ako.py due): an applicant's interview a day and an hour before, and its invite by
e-mail once per time. The postman's round runs it (outbox.send_due), once a minute, only while AKO_REMIND=1.

A channel is one async function: (cfg, http, the send) -> None (sent), "retry" (the next round tries again inside the
window) or why it never went. Telegram: the bot, to the private chat that tapped /start ako_... (bot_dm). E-mail: SMTP,
only with AKO_MAIL_FROM and SMTP_HOST set.
ponytail: WhatsApp is the next channel: Meta's Cloud API (WHATSAPP=1, WA_TOKEN, WA_PHONE_ID from the env, never the
repo), a template Meta approved per kind and language, to the package's phone. Upgrade: a _whatsapp() beside these,
SENDERS["whatsapp"], and ako.due adding ("d1"/"h1", "whatsapp") sends for a phone; ako_sends has no CHECK to change."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

import anyio.to_thread
import httpx

from . import logic, texts
from .bot import _tg
from .config import Config

log = logging.getLogger("kbtu.bot")

SMTP_WAIT = 10  # seconds: a hung mail server never holds the postman


def mail_on(cfg: Config) -> bool:
    return bool(cfg.ako_mail_from and cfg.smtp_host)


async def _telegram(cfg: Config, http: httpx.AsyncClient, m: dict) -> str | None:
    text, keys = logic.ako.message(f"ako_{m['kind']}", m["lang"], m["program"], m["at"], m["teams"])
    body = {"chat_id": m["to"], "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True},
            **({"reply_markup": {"inline_keyboard": keys}} if keys else {})}
    try:
        r = await _tg(cfg, http, "sendMessage", body)
    except httpx.HTTPError:
        return "retry"
    if r.status_code == 200:
        return None
    if r.status_code == 403:  # blocked the bot
        return "blocked"
    return "retry" if r.status_code == 429 or r.status_code >= 500 else f"telegram {r.status_code}"


def _mail(cfg: Config, m: dict) -> EmailMessage:
    words = texts.pick(texts.AKO_MAIL, m["lang"])
    msg = EmailMessage()
    msg["From"], msg["To"] = cfg.ako_mail_from, m["to"]
    msg["Subject"] = words[m["kind"]].format(program=m["program"])
    msg["Message-ID"] = make_msgid(domain=cfg.domain)
    msg.set_content(words["body"].format(program=m["program"], when=texts.when(m["at"], m["lang"]), teams=m["teams"] or "", org=m["org"]))
    if m["ics"]:
        msg.add_attachment(m["ics"].encode(), maintype="text", subtype="calendar", filename="interview.ics", params={"method": "PUBLISH"})
    return msg


def _smtp(cfg: Config, msg: EmailMessage) -> None:
    """One message through the configured server: 465 is TLS from the start, any other port upgrades when offered."""
    if cfg.smtp_port == 465:
        s = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=SMTP_WAIT, context=ssl.create_default_context())
    else:
        s = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=SMTP_WAIT)
    with s:
        if cfg.smtp_port != 465:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls(context=ssl.create_default_context())
        if cfg.smtp_user:
            s.login(cfg.smtp_user, cfg.smtp_password)
        s.send_message(msg)


async def _email(cfg: Config, http: httpx.AsyncClient, m: dict) -> str | None:
    try:
        await anyio.to_thread.run_sync(_smtp, cfg, _mail(cfg, m))
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, smtplib.SMTPSenderRefused, smtplib.SMTPAuthenticationError) as exc:
        return type(exc).__name__  # the class alone: a refused recipient's error carries the address
    except (OSError, smtplib.SMTPException):  # the network, a timeout, a server gone mid-way
        return "retry"
    return None


SENDERS = {"telegram": _telegram, "email": _email}


async def tick(cfg: Config, http: httpx.AsyncClient, con) -> None:
    """The round's reminders: nothing at all with AKO_REMIND off (ako.BOT empty), and at most once a minute."""
    if not logic.ako.BOT or not await anyio.to_thread.run_sync(logic._once, con, "ako_minute", str(logic.now() // 60)):
        return
    down: set[str] = set()  # a channel that failed this round waits for the next: one hung server, one timeout a round
    for m in await anyio.to_thread.run_sync(logic.ako.due, con, mail_on(cfg)):
        error = "retry" if m["channel"] in down else await SENDERS[m["channel"]](cfg, http, m)
        if error == "retry":
            down.add(m["channel"])
        if error not in (None, "retry"):
            log.warning("ako: %s by %s for package %s: %s", m["kind"], m["channel"], m["app"], error)
        await anyio.to_thread.run_sync(logic.ako.sent, con, m, error)
