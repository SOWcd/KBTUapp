"""Support: a private ledger, receipt decisions and an optional public name + tier.

Amounts never enter achievement counts: those carry only the tier. Stars' anonymous
charge table remains the replay guard even after an account and its ledger are erased.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import media, receipt
from ..db import tx
from . import core, seats
from .core import ApiError, Viewer, one, rows, shown_name

CONSENT = "sp1"
AMOUNT_CONSENT = "sa1"  # a second switch: the total beside the name, only while sp1 is on too
RECEIPT_CONSENT = "dn1"
STAR_KZT = 10  # A fixed recognition rate, not a market price; owner confirms before rollout.
TIERS = (1, 5000, 20000)
RECEIPTS_A_DAY = 5
FRESH = 7 * 86400
KEEP = 30 * 86400
PENDING_KEEP = 90 * 86400
MAX_AMOUNT = 100_000_000
_LAST = "LEFT JOIN sponsor_consents c ON c.id = (SELECT id FROM sponsor_consents WHERE user_id = u.id ORDER BY id DESC LIMIT 1)"
_NAMES = "u.nick, u.tg_first_name, s.first_name, s.last_name"


def tier(amount: int) -> int:
    return sum(amount >= n for n in TIERS)


def total(con, uid: int) -> int:
    return one(con, "SELECT COALESCE(SUM(amount), 0) FROM donations WHERE user_id = ? AND status = 'confirmed'", uid)[0]


def public(con, uid: int) -> bool:
    return bool(one(con, f"""SELECT 1 FROM users u {_LAST} WHERE u.id = ? AND u.tg_id > 0
        AND u.banned_at IS NULL AND c.show = 1 AND c.version = ?""", uid, CONSENT))


def owner(con, v: Viewer) -> bool:
    return bool(one(con, "SELECT 1 FROM users WHERE id = ? AND role = 'admin' AND is_founder = 1 AND banned_at IS NULL AND tg_id > 0", v.id))


def _owner(con, v: Viewer) -> None:
    if not owner(con, v):
        raise ApiError("forbidden")


def sync_medal(con, uid: int) -> None:
    """Inside the payment/review transaction, including a correction or Undo. No public bot award card."""
    level = tier(total(con, uid))
    if not level:
        con.execute("DELETE FROM achievement_grants WHERE user_id = ? AND code = 'sponsor'", (uid,))
        con.execute("DELETE FROM achievement_levels WHERE user_id = ? AND code = 'sponsor'", (uid,))
        return
    con.execute("""INSERT INTO achievement_grants (user_id, code, created_at)
        SELECT ?, 'sponsor', ? WHERE NOT EXISTS (SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'sponsor')""", (uid, core.now(), uid))
    con.execute("""INSERT INTO achievement_levels (user_id, code, level, reached_at) VALUES (?, 'sponsor', ?, ?)
        ON CONFLICT (user_id, code) DO UPDATE SET level = excluded.level, reached_at = excluded.reached_at
        WHERE achievement_levels.level != excluded.level""", (uid, level, core.now()))


def mine(con, v: Viewer) -> dict:
    with tx(con, write=False):
        amount = total(con, v.id)
        consent = one(con, "SELECT * FROM sponsor_consents WHERE user_id = ? ORDER BY id DESC LIMIT 1", v.id)
        show = bool(consent and consent["show"] and consent["version"] == CONSENT)
        return {"total": amount, "tier": tier(amount), "thresholds": TIERS, "starRate": STAR_KZT,
                "version": CONSENT, "amountVersion": AMOUNT_CONSENT, "receiptConsent": RECEIPT_CONSENT,
                "show": show, "showAmount": show and consent["amount"] == AMOUNT_CONSENT,
                "rev": consent["id"] if consent else None,
                "receipts": [{"id": r["id"], "status": r["status"], "amount": r["amount"], "at": r["created_at"]}
                             for r in rows(con, "SELECT * FROM donations WHERE user_id = ? AND source = 'receipt' ORDER BY id DESC LIMIT 30", v.id)]}


def listing(con) -> list[dict]:
    """The honour board. Tier first (already public), then the shown totals, largest first; a hidden total sorts after
    the shown ones of its tier by name, so a place never hints at an amount nobody agreed to show."""
    return [{"name": shown_name(r), "tier": r["level"], **({"amount": r["shown"]} if r["shown"] is not None else {})}
            for r in rows(con, f"""SELECT {_NAMES}, l.level, CASE WHEN c.amount = ? THEN
              (SELECT SUM(amount) FROM donations WHERE user_id = u.id AND status = 'confirmed') END AS shown
        FROM achievement_levels l JOIN users u ON u.id = l.user_id AND l.code = 'sponsor'
        LEFT JOIN students s ON s.user_id = u.id {_LAST}
        WHERE u.tg_id > 0 AND u.banned_at IS NULL AND c.show = 1 AND c.version = ?
        ORDER BY l.level DESC, shown IS NULL, shown DESC, COALESCE(u.nick, s.first_name, u.tg_first_name), u.id""",
                              AMOUNT_CONSENT, CONSENT)]


def answer(con, v: Viewer, payer: int, body: dict, field: str = "show") -> dict:
    """One switch: field 'show' (the name, sp1) or 'amount' (the total beside it, sa1). Each row holds both."""
    if type(body.get("show")) is not bool:
        raise ApiError("bad_input")
    on, version = body["show"], (CONSENT if field == "show" else AMOUNT_CONSENT)
    with tx(con):
        if not one(con, "SELECT 1 FROM users WHERE id = ? AND tg_id = ? AND banned_at IS NULL", v.id, payer):
            raise ApiError("forbidden")
        last = one(con, "SELECT * FROM sponsor_consents WHERE user_id = ? ORDER BY id DESC LIMIT 1", v.id)
        named = bool(last and last["show"] and last["version"] == CONSENT)
        if on:
            if body.get("consent") != version or not (body.get("rev") is None or type(body["rev"]) is int):
                raise ApiError("bad_input", "consent")
            # The amount needs the name on: a figure beside nobody would be no honour, only a leak.
            if body.get("rev") != (last["id"] if last else None) or not total(con, v.id) or (field == "amount" and not named):
                raise ApiError("conflict")
        # A late withdrawal always wins; a late yes must name the current revision. Hiding the name hides the
        # amount too, so showing the name again later never brings the figure back unasked.
        if field == "show":
            show, amount = on, (last["amount"] if on and named else None)
        else:
            show, amount = named, (AMOUNT_CONSENT if on else None)
        con.execute("INSERT INTO sponsor_consents (user_id, version, show, amount, at) VALUES (?, ?, ?, ?, ?)",
                    (v.id, CONSENT, int(show), amount, core.now()))
    return mine(con, v)


def receipt_open(con, v: Viewer, payer: int, cfg, consent: str) -> None:
    with tx(con):
        _receipt_slot(con, v, payer, cfg, consent)
        core.upload_attempt(con, v, "receipt")


def _receipt_slot(con, v: Viewer, payer: int, cfg, consent: str) -> None:
    if not cfg.donate_phone:
        raise ApiError("not_found")
    if consent != RECEIPT_CONSENT:
        raise ApiError("forbidden", "donation_consent")
    if not one(con, "SELECT 1 FROM users WHERE id = ? AND tg_id = ? AND banned_at IS NULL AND delete_at IS NULL", v.id, payer):
        raise ApiError("forbidden")
    # Count every submitted row, even one already decided: decisions must not refund the daily limit.
    if one(con, "SELECT COUNT(*) FROM donations WHERE user_id = ? AND source = 'receipt' AND flags != 'manual' AND created_at > ?", v.id, core.now() - 86400)[0] >= RECEIPTS_A_DAY:
        raise ApiError("rate_limited", "donation_receipts")


def add_receipt(con, v: Viewer, payer: int, cfg, saved: dict, read: dict | None, consent: str) -> dict:
    with tx(con):
        _receipt_slot(con, v, payer, cfg, consent)
        got = read or {}
        amount = got.get("amount")
        # Reuse the event reader's amount, payee, freshness, reuse checks and strict clean check.
        expected = {"price": amount if type(amount) is int and 0 < amount <= MAX_AMOUNT else 0,
                    "pay_to_name": cfg.donate_recipient, "created_at": core.now() - FRESH}
        flags = seats._receipt_flags(con, expected, saved["sha256"], read)
        # An image proves little (an edited sum, a friend's receipt): it may earn only the first tier, which one Star
        # also buys. A receipt that would lift the total to a higher tier waits for the creator.
        clean = bool(expected["price"] and got.get("bank") == "kaspi"
                     and tier(total(con, v.id) + expected["price"]) <= 1
                     and seats._receipt_clean(con, expected, saved["sha256"], read, flags))
        if clean and seats._audit():
            flags, clean = seats.SPOT, False
        elif not clean and not flags:
            flags = seats.PARTIAL
        fid = con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at)
            VALUES (?, 'receipt', 'image/webp', ?, ?, ?, ?, ?, ?)""",
                          (saved["sha256"], saved["bytes"], saved["width"], saved["height"], saved["path"], v.id, core.now())).lastrowid
        did = con.execute("""INSERT INTO donations (user_id, source, status, amount, file_id, sha256, receipt_no,
            read_amount, recipient_name, sender_name, paid_at, flags, auto, consent, created_at, reviewed_at, purge_at)
            VALUES (?, 'receipt', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (v.id, "confirmed" if clean else "pending", amount if clean else None, fid, saved["sha256"],
                           got.get("no"), amount, got.get("recipient"), got.get("sender"), got.get("paid_at"), flags, int(clean),
                           RECEIPT_CONSENT, core.now(), core.now() if clean else None, core.now() + KEEP if clean else None)).lastrowid
        if clean:
            sync_medal(con, v.id)
            _notify(con, v.id, did, 0, "confirmed")
    return mine(con, v)


def add_manual(con, uid: int, amount: int, day: str | None = None, again: bool = False) -> int:
    """`admin donation add`: a transfer the creator checked by hand (Kaspi, outside the app), confirmed at once.
    The CHECK on source can't be altered, so it is a receipt row with no file and flags 'manual': the queue, review
    and sweep skip it (no file), the daily receipt cap doesn't count it. It never touches the donor's consent."""
    if not 0 < amount <= 10_000_000:
        raise ApiError("bad_input", "amount")
    at = core.now()
    if day:
        at = int(datetime.strptime(day, "%Y-%m-%d").replace(hour=12, tzinfo=timezone(timedelta(hours=5))).timestamp())
        if at > core.now() + 86400:
            raise ApiError("bad_input", "date")
    start = at - (at + 5 * 3600) % 86400  # the Almaty day it falls on
    with tx(con):
        if not again and one(con, """SELECT 1 FROM donations WHERE user_id = ? AND flags = 'manual' AND amount = ?
                AND created_at >= ? AND created_at < ?""", uid, amount, start, start + 86400):
            raise ApiError("conflict", "the same amount that day already: --again to add it anyway")
        did = con.execute("""INSERT INTO donations (user_id, source, status, amount, flags, consent, created_at, reviewed_at)
            VALUES (?, 'receipt', 'confirmed', ?, 'manual', 'manual', ?, ?)""", (uid, amount, at, core.now())).lastrowid
        sync_medal(con, uid)
        core.log_action(con, None, "donation_by_hand", f"user:{uid}", json.dumps({"donation": did, "amount": amount}))
    return did


def remove_manual(con, did: int) -> int:
    """`admin donation remove`: a hand-added row typed wrong; the medal follows. Only manual rows."""
    with tx(con):
        d = one(con, "SELECT user_id, amount FROM donations WHERE id = ? AND flags = 'manual'", did)
        if not d:
            raise ApiError("not_found")
        con.execute("DELETE FROM donations WHERE id = ?", (did,))
        sync_medal(con, d["user_id"])
        core.log_action(con, None, "donation_by_hand_undo", f"user:{d['user_id']}", json.dumps({"donation": did, "amount": d["amount"]}))
    return d["user_id"]


def _notify(con, uid: int, did: int, revision: int, status: str) -> None:
    # Give the creator time to Undo. The bot rechecks the revision and decision before delivery.
    seats.notify(con, uid, "donation_" + status, f"dn:{did}:{revision}", after=core.now() + 45)


def queue(con, v: Viewer) -> list[dict]:
    _owner(con, v)
    return [{"id": r["id"], "name": shown_name(r), "status": r["status"], "amount": r["amount"],
             "readAmount": r["read_amount"], "recipient": r["recipient_name"], "sender": r["sender_name"],
             "no": r["receipt_no"], "paidAt": r["paid_at"], "flags": r["flags"].split(",") if r["flags"] else [],
             "auto": bool(r["auto"]), "image": r["file_id"] is not None, "at": r["created_at"],
             "revision": r["revision"], "undo": bool(r["undo"])} for r in rows(con, f"""SELECT d.*, {_NAMES}
        FROM donations d JOIN users u ON u.id = d.user_id LEFT JOIN students s ON s.user_id = u.id
        WHERE d.source = 'receipt' AND d.file_id IS NOT NULL AND COALESCE(d.purge_at, d.created_at + ?) > ?
        ORDER BY d.status != 'pending', d.created_at, d.id LIMIT 200""", PENDING_KEEP, core.now())]


def review(con, v: Viewer, did: int, body: dict) -> None:
    action, amount = body.get("action"), body.get("amount")
    if action not in ("confirm", "reject", "undo") or type(body.get("revision")) is not int:
        raise ApiError("bad_input")
    if action == "confirm" and (type(amount) is not int or not 0 < amount <= MAX_AMOUNT):
        raise ApiError("bad_input", "amount")
    with tx(con):
        _owner(con, v)
        d = one(con, "SELECT * FROM donations WHERE id = ? AND source = 'receipt'", did)
        if not d:
            raise ApiError("not_found")
        if d["revision"] != body["revision"]:
            raise ApiError("conflict")
        at = core.now()
        if not d["file_id"] or (d["purge_at"] or d["created_at"] + PENDING_KEEP) <= at:
            raise ApiError("conflict", "expired")
        if action == "undo":
            if not d["undo"]:
                raise ApiError("conflict")
            old = json.loads(d["undo"])
            status, amount, auto, reviewed_at, purge_at = (old[k] for k in ("status", "amount", "auto", "reviewed_at", "purge_at"))
            undo = None
        else:
            status, auto, reviewed_at = ("confirmed" if action == "confirm" else "rejected"), 0, at
            purge_at = d["purge_at"] or at + KEEP
            undo = json.dumps({k: d[k] for k in ("status", "amount", "auto", "reviewed_at", "purge_at")})
            if action == "reject":
                amount = None
        con.execute("""UPDATE donations SET status = ?, amount = ?, auto = ?, reviewed_at = ?, reviewed_by = ?,
            revision = revision + 1, undo = ?, purge_at = ? WHERE id = ?""",
                    (status, amount, auto, reviewed_at, v.id, undo, purge_at, did))
        sync_medal(con, d["user_id"])
        if status != "pending":
            _notify(con, d["user_id"], did, d["revision"] + 1, status)


def image_path(con, v: Viewer, did: int) -> str:
    d = one(con, """SELECT d.user_id, f.path FROM donations d JOIN files f ON f.id = d.file_id
        WHERE d.id = ? AND COALESCE(d.purge_at, d.created_at + ?) > ?""", did, PENDING_KEEP, core.now())
    if not d or not (d["user_id"] == v.id or owner(con, v)):
        raise ApiError("not_found")
    return d["path"]


def sweep(con) -> None:
    """Nightly: release the private files, preserving only the ledger and reuse fingerprints."""
    from .account import _drop_unused
    root = Path(one(con, "PRAGMA database_list")["file"]).resolve().parent / "receipts"
    at = core.now()
    with tx(con):
        due = rows(con, """SELECT id, file_id, user_id, status, revision FROM donations WHERE source = 'receipt' AND file_id IS NOT NULL
            AND (purge_at <= ? OR (purge_at IS NULL AND created_at <= ?))""", at, at - PENDING_KEEP)
        for d in due:
            con.execute("""UPDATE donations SET file_id = NULL, recipient_name = NULL, sender_name = NULL, paid_at = NULL, undo = NULL,
                status = CASE WHEN status = 'pending' THEN 'rejected' ELSE status END WHERE id = ?""", (d["id"],))
            # Erase before dropping the file row: an interrupted unlink can be retried tomorrow.
            f = one(con, "SELECT path FROM files WHERE id = ?", d["file_id"])
            if f and not one(con, "SELECT 1 FROM files WHERE path = ? AND kind = 'receipt' AND id != ?", f["path"], d["file_id"]):
                media.drop(root, [f["path"]])
            _drop_unused(con, d["file_id"])
            if d["status"] == "pending":
                _notify(con, d["user_id"], d["id"], d["revision"], "rejected")
    # A worker can exit between writing an image and committing its row. Give in-flight uploads a day to finish.
    paths = {r[0] for r in rows(con, "SELECT f.path FROM donations d JOIN files f ON f.id = d.file_id")}
    for f in (root / receipt.DONATION_DIR).glob("*/*.*"):
        path = str(f.relative_to(root)).split(".", 1)[0]
        if path not in paths:
            try:
                if f.stat().st_mtime < at - 86400:
                    f.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
