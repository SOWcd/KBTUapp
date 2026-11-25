"""Sponsor payments, private receipts and the Sponsors list (shown by default, hidden by the donor's own switch)
through the real HTTP boundary.

All people, payment identifiers and receipt images here are made up. CI runs these tests.
"""
from __future__ import annotations

import dataclasses
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from kbtu import admin, app as server, db, logic, media, outbox, receipt, texts
from kbtu.logic import donations, seats, stars
from test_core import delete_now, env, login, set_clock, tma  # noqa: F401
from test_review_seats import _paid, _shot
from test_stars import Telegram, checkout, hear, payment, wire


@pytest.fixture
def support(env, monkeypatch):
    _, cfg = env
    cfg = dataclasses.replace(cfg, donate_phone="+77000000000", donate_recipient="Arman A.", admins=frozenset({60, 63}))
    c = TestClient(server.create(cfg))
    ids = {tg: login(c, tg, name)["id"] for tg, name in ((7, "aidar"), (8, "bek"), (60, "owner"), (63, "admin"), (64, "mod"))}
    con = db.connect(cfg.db_path)
    con.execute("UPDATE users SET is_founder = 1 WHERE id = ?", (ids[60],))
    con.execute("UPDATE users SET role = 'moderator' WHERE id = ?", (ids[64],))
    clock = [int(time.time())]
    set_clock(monkeypatch, lambda: clock[0])
    monkeypatch.setattr(stars, "now", lambda: clock[0])
    monkeypatch.setattr(seats, "_audit", lambda: False)
    yield c, cfg, con, ids, clock
    con.close()


def fields(now, **changes):
    return {"bank": "kaspi", "amount": 2500, "recipient": "Arman A.", "sender": "Testov A.",
            "no": "123456789012345678", "paid_at": now - 60, **changes}


def upload(support, monkeypatch, read, tg=7, shade=240):
    c, _, _, _, _ = support
    monkeypatch.setattr(receipt, "read", lambda im: read)
    r = c.post(f"/api/donate/receipt?consent={donations.RECEIPT_CONSENT}", headers=tma(tg), content=_shot(shade))
    assert r.status_code == 200, r.text
    return r.json()


def decide(support, did, action, amount=None, tg=60, revision=None):
    c, _, con, _, _ = support
    rev = con.execute("SELECT revision FROM donations WHERE id = ?", (did,)).fetchone()[0]
    return c.post(f"/api/admin/donations/{did}/review", headers=tma(tg),
                  json={"action": action, "amount": amount, "revision": rev if revision is None else revision})


def mine(support, tg=7):
    return support[0].get("/api/donate", headers=tma(tg)).json()


def consent(support, show, **changes):
    return support[0].put("/api/donate/consent", headers=tma(7),
                          json={"show": show, "consent": donations.CONSENT, "rev": mine(support)["rev"], **changes})


def test_only_telegram_confirmation_counts_once_and_upgrades(support):
    c, cfg, con, ids, _ = support
    wire(c)
    assert c.post("/api/donate/stars", headers=tma(7), json={"amount": 500}).status_code == 200
    hear(cfg, Telegram([checkout()], []))
    assert mine(support)["total"] == 0
    assert not con.execute("SELECT 1 FROM donations").fetchone()
    for update, charge, amount, level in ((2, "s1", 499, 1), (3, "s2", 1, 2), (4, "s3", 1500, 3)):
        p = payment(update, charge=charge, amount=amount)
        hear(cfg, Telegram([p], []))
        hear(cfg, Telegram([p], []))
        assert mine(support)["tier"] == level
    assert mine(support)["total"] == 2000 * donations.STAR_KZT
    assert con.execute("SELECT COUNT(*) FROM donations").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'sponsor'", (ids[7],)).fetchone()[0] == 1
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'sponsor'", (ids[7],)).fetchone()[0] == 3
    assert {tuple(r) for r in con.execute("SELECT star_rate, consent FROM donations")} == {(donations.STAR_KZT, stars.CONSENT)}
    assert not con.execute("SELECT 1 FROM bot_outbox WHERE user_id = ?", (ids[7],)).fetchone()
    assert c.get("/api/sponsors", headers=tma(8)).json() == []


def test_old_invoices_keep_the_old_anonymous_promise(support):
    _, cfg, con, _, _ = support
    assert not stars.checkout_ok(cfg.bot_token, {"invoice_payload": "don:50", "currency": "XTR", "total_amount": 50}, 7)
    old = payment(charge="legacy")
    old["message"]["successful_payment"]["invoice_payload"] = "don:50"
    hear(cfg, Telegram([old], []))
    assert con.execute("SELECT amount FROM star_gifts WHERE charge_id = 'legacy'").fetchone()[0] == 50
    assert mine(support)["total"] == 0
    # An old anonymous charge is never reassigned by a changed/replayed update.
    hear(cfg, Telegram([payment(charge="legacy")], []))
    assert mine(support)["total"] == 0


def test_telegram_only_donor_can_erase_linked_payments(support):
    c, cfg, con, _, _ = support
    assert c.get("/api/me", headers=tma(70)).status_code == 200
    hear(cfg, Telegram([payment(payer=70)], []))
    assert mine(support, 70)["tier"] == 1
    delete_now(c, cfg, tma(70))
    assert mine(support, 70)["total"] == 0
    assert not con.execute("SELECT 1 FROM donations").fetchone()


def test_failed_medal_write_rolls_back_the_payment_and_replay_grants_once(support, monkeypatch):
    _, cfg, con, ids, _ = support
    sync = donations.sync_medal
    def fail(*args):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(donations, "sync_medal", fail)
    update = payment(uid=9, charge="atomic")
    assert hear(cfg, Telegram([update], [])) == 9
    assert not con.execute("SELECT 1 FROM donations").fetchone()
    assert not con.execute("SELECT 1 FROM star_gifts WHERE charge_id = 'atomic'").fetchone()
    monkeypatch.setattr(donations, "sync_medal", sync)
    for _ in range(2):
        hear(cfg, Telegram([update], []))
    assert mine(support)["total"] == 50 * donations.STAR_KZT
    assert con.execute("SELECT COUNT(*) FROM donations").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM achievement_grants WHERE user_id = ? AND code = 'sponsor'", (ids[7],)).fetchone()[0] == 1


@pytest.mark.parametrize("amount,level", [(0, 0), (1, 1), (4999, 1), (5000, 2), (19999, 2), (20000, 3), (99999, 3)])
def test_tier_boundaries(amount, level):
    assert donations.tier(amount) == level


def test_clean_kaspi_receipt_is_confirmed_and_granted_in_the_upload(support, monkeypatch):
    c, _, con, ids, clock = support
    got = upload(support, monkeypatch, fields(clock[0]))
    assert (got["total"], got["tier"], got["show"], got["showAmount"]) == (2500, 1, True, True)
    [r] = got["receipts"]
    assert r["status"] == "confirmed" and r["amount"] == 2500
    stored = con.execute("SELECT * FROM donations WHERE id = ?", (r["id"],)).fetchone()
    assert stored["auto"] == 1 and stored["flags"] == "" and stored["consent"] == donations.RECEIPT_CONSENT
    assert stored["purge_at"] == clock[0] + donations.KEEP
    assert con.execute("SELECT 1 FROM achievement_grants WHERE user_id = ? AND code = 'sponsor'", (ids[7],)).fetchone()
    q = c.get("/api/admin/donations", headers=tma(60)).json()[0]
    assert q["auto"] and q["readAmount"] == q["amount"] == 2500


def test_a_clean_receipt_never_lifts_past_the_first_tier_by_itself(support, monkeypatch):
    c, _, _, _, clock = support
    big = upload(support, monkeypatch, fields(clock[0], amount=20000))
    assert big["receipts"][0]["status"] == "pending" and big["tier"] == 0
    # Two clean 2 500 receipts: the first passes, the one reaching 5 000 waits.
    first = upload(support, monkeypatch, fields(clock[0], no="223456789012345678", paid_at=clock[0] - 120), shade=241)
    assert (first["total"], first["tier"]) == (2500, 1)
    second = upload(support, monkeypatch, fields(clock[0], no="323456789012345678", paid_at=clock[0] - 180), shade=242)
    assert (second["total"], second["tier"]) == (2500, 1) and second["receipts"][0]["status"] == "pending"
    assert c.get("/api/admin/donations", headers=tma(60)).json()[0]["flags"] == [seats.PARTIAL]


@pytest.mark.parametrize("heading,confirmed", [
    ("Kaspi.kz", True), ("KASPI BANK", True), ("14:55\n75%\nKaspi.kz", True),
    ("Halyk", False), ("Forte", False), ("Other bank\nKaspi.kz", False), ("", False),
])
def test_only_kaspi_issuer_headings_allow_auto_confirmation(support, monkeypatch, heading, confirmed):
    _, _, _, _, clock = support
    when = datetime.fromtimestamp(clock[0] - 60, receipt.ASTANA).strftime("%d.%m.%Y %H:%M")
    read = receipt.parse(f"{heading}\nTransfer completed\n2 500 \u20b8\nArman A.\n"
                         f"No 123456789012345678\n{when}\nSender Testov A.\nRecipient bank Kaspi Gold")
    assert read["amount"] == 2500 and read["recipient"] == "Arman A."
    assert (read.get("bank") == "kaspi") is confirmed
    got = upload(support, monkeypatch, read)
    assert got["receipts"][0]["status"] == ("confirmed" if confirmed else "pending")


@pytest.mark.parametrize("change", [
    {"bank": "halyk"}, {"bank": None}, {"amount": None}, {"no": None}, {"recipient": None},
    {"paid_at": None}, {"recipient": "Arman B."}, {"signed": True}, {"amount": 0},
    {"amount": donations.MAX_AMOUNT + 1}, {"paid_at": 1}, {"paid_at": 9_999_999_999},
])
def test_other_banks_and_partial_or_doubtful_readings_wait_for_creator(support, monkeypatch, change):
    c, _, _, _, clock = support
    got = upload(support, monkeypatch, fields(clock[0], **change))
    assert got["total"] == got["tier"] == 0 and got["receipts"][0]["status"] == "pending"
    q = c.get("/api/admin/donations", headers=tma(60)).json()[0]
    assert q["readAmount"] == change.get("amount", 2500)
    assert q["amount"] is None and q["flags"]
    assert decide(support, q["id"], "confirm", 5000).status_code == 204
    assert mine(support)["tier"] == 2 and mine(support)["total"] == 5000


@pytest.mark.parametrize("read,flag", [(None, "ocr_unavailable"), ({}, "unreadable")])
def test_unread_upload_still_reaches_the_queue(support, monkeypatch, read, flag):
    c, _, _, _, _ = support
    upload(support, monkeypatch, read)
    assert c.get("/api/admin/donations", headers=tma(60)).json()[0]["flags"] == [flag]


def test_recipient_configuration_is_private_and_required_for_automation(support, monkeypatch):
    c, cfg, con, _, clock = support
    assert cfg.donate_recipient not in repr(cfg)
    for i, name in enumerate(("", "Arman")):
        other = TestClient(server.create(dataclasses.replace(cfg, donate_recipient=name)))
        got = upload((other, cfg, con, None, clock), monkeypatch, fields(clock[0], no=str(123456789012345670 + i), paid_at=clock[0] - i), shade=200 + i)
        assert got["receipts"][0]["status"] == "pending"
    assert cfg.donate_recipient not in c.get("/api/me", headers=tma(7)).text


def test_audit_uses_event_share_and_cannot_be_rerolled(support, monkeypatch):
    c, _, _, _, clock = support
    monkeypatch.setattr(seats, "_audit", lambda: True)
    first = upload(support, monkeypatch, fields(clock[0]))
    assert first["receipts"][0]["status"] == "pending"
    assert c.get("/api/admin/donations", headers=tma(60)).json()[0]["flags"] == [seats.SPOT]
    monkeypatch.setattr(seats, "_audit", lambda: False)
    # A changed receipt number and changed file still retain the minute/sum/payee collision.
    second = upload(support, monkeypatch, fields(clock[0], no="223456789012345678"), shade=241)
    assert second["total"] == 0
    assert "duplicate" in c.get("/api/admin/donations", headers=tma(60)).json()[1]["flags"]


@pytest.mark.parametrize("same_file", [True, False])
def test_file_or_number_reuse_never_auto_confirms(support, monkeypatch, same_file):
    c, _, _, _, clock = support
    upload(support, monkeypatch, fields(clock[0]))
    read = fields(clock[0], no="223456789012345678" if same_file else "123456789012345678", paid_at=clock[0] - 120)
    got = upload(support, monkeypatch, read, tg=8, shade=240 if same_file else 241)
    assert got["total"] == 0
    pending = next(r for r in c.get("/api/admin/donations", headers=tma(60)).json() if r["status"] == "pending")
    assert "duplicate" in pending["flags"]


def test_reuse_checks_work_across_events_and_donations_in_both_directions(support, monkeypatch):
    c, cfg, _, _, clock = support
    con, eid = _paid(c, cfg, seats=2)
    monkeypatch.setattr(receipt, "read", lambda im: fields(clock[0], amount=2000))
    c.post(f"/api/events/{eid}/registration", headers=tma(10), json={})
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(10), content=_shot()).status_code == 200
    got = upload(support, monkeypatch, fields(clock[0], amount=2000), shade=241)
    assert got["receipts"][0]["status"] == "pending"
    assert "duplicate" in c.get("/api/admin/donations", headers=tma(60)).json()[0]["flags"]
    new = fields(clock[0], amount=2000, no="223456789012345678", paid_at=clock[0] - 120)
    upload(support, monkeypatch, new, shade=242)
    c.post(f"/api/events/{eid}/registration", headers=tma(11), json={})
    monkeypatch.setattr(receipt, "read", lambda im: new)
    assert c.post(f"/api/events/{eid}/receipt", headers=tma(11), content=_shot(243)).status_code == 200
    row = con.execute("SELECT flags FROM receipts ORDER BY id DESC LIMIT 1").fetchone()
    assert "duplicate" in row["flags"]
    con.close()


def test_creator_decisions_correct_totals_and_can_be_undone(support, monkeypatch):
    _, cfg, con, ids, clock = support
    hear(cfg, Telegram([payment(amount=100)], []))
    did = upload(support, monkeypatch, {"amount": 2000})["receipts"][0]["id"]
    assert decide(support, did, "confirm", 19000).status_code == 204
    assert (mine(support)["total"], mine(support)["tier"]) == (20000, 3)
    assert decide(support, did, "confirm", 4000).status_code == 204
    assert (mine(support)["total"], mine(support)["tier"]) == (5000, 2)
    assert decide(support, did, "undo").status_code == 204
    assert mine(support)["tier"] == 3
    assert decide(support, did, "reject").status_code == 204
    assert mine(support)["total"] == 1000 and mine(support)["tier"] == 1
    assert decide(support, did, "undo").status_code == 204
    assert mine(support)["tier"] == 3
    assert decide(support, did, "undo").status_code == 409
    assert decide(support, did, "reject", revision=0).status_code == 409
    assert con.execute("SELECT level FROM achievement_levels WHERE user_id = ? AND code = 'sponsor'", (ids[7],)).fetchone()[0] == 3
    # Undo restores the prior decision's retention deadline.
    assert con.execute("SELECT purge_at FROM donations WHERE id = ?", (did,)).fetchone()[0] == clock[0] + donations.KEEP


@pytest.mark.parametrize("amount", [None, 0, -1, True, 1.5, "5000", donations.MAX_AMOUNT + 1])
def test_confirmation_requires_a_positive_integer_amount(support, monkeypatch, amount):
    did = upload(support, monkeypatch, {})["receipts"][0]["id"]
    assert decide(support, did, "confirm", amount).status_code == 400
    assert mine(support)["total"] == 0


def test_receipts_and_amounts_are_private_even_from_other_staff(support, monkeypatch):
    c, _, _, ids, clock = support
    did = upload(support, monkeypatch, fields(clock[0]))["receipts"][0]["id"]
    assert consent(support, False).status_code == 200  # hidden: the medal leaves other people's view too
    for tg in (8, 63, 64):
        assert c.get("/api/admin/donations", headers=tma(tg)).status_code == 403
        assert decide(support, did, "reject", tg=tg).status_code == 403
        assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(tg)).status_code == 404
        assert mine(support, tg)["total"] == 0
        card = c.get(f"/api/users/{ids[7]}", headers=tma(tg)).json()
        assert "sponsor" not in [a["code"] for a in card["awards"]["achievements"]]
    for tg in (7, 60):
        r = c.get(f"/api/donate/receipts/{did}/image", headers=tma(tg))
        assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    for path, tg in (("/api/donate", 7), ("/api/sponsors", 8), ("/api/admin/donations", 60)):
        assert c.get(path, headers=tma(tg)).headers["cache-control"] == "private, no-store"
        assert c.get(path).status_code == 403
    assert c.get("/api/admin/awards/sponsor/people", headers=tma(63)).status_code in (400, 403)
    assert c.post("/api/admin/grants", headers=tma(60), json={"userId": ids[8], "code": "sponsor"}).status_code == 400
    assert c.post("/api/share", headers=tma(7), json={"kind": "aw", "code": "sponsor"}).status_code == 400


def test_shown_by_default_and_a_hide_wins(support, monkeypatch):
    c, _, con, ids, clock = support
    did = upload(support, monkeypatch, fields(clock[0], amount=5107))["receipts"][0]["id"]
    assert decide(support, did, "confirm", 5107).status_code == 204
    c.patch("/api/me", headers=tma(7), json={"showcase": ["sponsor"]})
    assert c.get("/api/sponsors", headers=tma(8)).json() == [{"name": "Aidar T", "tier": 2, "amount": 5107}]
    card = c.get(f"/api/users/{ids[7]}", headers=tma(8)).json()
    medal = next(a for a in card["awards"]["achievements"] if a["code"] == "sponsor")
    assert medal["count"] == medal["level"] == 2 and medal["at"] is None and medal["rarity"] == 0
    assert "5107" not in str(card)  # never on a profile
    assert consent(support, True, consent="old").status_code == 400
    assert consent(support, "yes").status_code == 400
    rev = mine(support)["rev"]
    assert consent(support, False, consent="old", rev=None).status_code == 200  # an old app's hide: never refused
    assert consent(support, True, rev=rev).status_code == 409  # a late show never undoes it
    assert mine(support)["show"] is False and c.get("/api/sponsors", headers=tma(8)).json() == []
    assert "sponsor" not in str(c.get(f"/api/users/{ids[7]}", headers=tma(8)).json())
    assert consent(support, True).status_code == 200  # shown again, the total stays hidden until its own switch
    assert c.get("/api/sponsors", headers=tma(8)).json() == [{"name": "Aidar T", "tier": 2}]
    con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids[7],))
    assert c.get("/api/sponsors", headers=tma(8)).json() == []


def shown(support, on, tg=7, **changes):
    return support[0].put("/api/donate/amount", headers=tma(tg),
                          json={"show": on, "consent": donations.AMOUNT_CONSENT, "rev": mine(support, tg)["rev"], **changes})


def board(support):
    return [(p["tier"], p.get("amount")) for p in support[0].get("/api/sponsors", headers=tma(64)).json()]


def test_amount_is_shown_beside_the_name_and_hides_on_its_own(support, monkeypatch):
    c, _, con, ids, clock = support
    did = upload(support, monkeypatch, fields(clock[0], amount=5107))["receipts"][0]["id"]
    assert decide(support, did, "confirm", 5107).status_code == 204
    assert mine(support)["showAmount"] is True and board(support) == [(2, 5107)]
    assert shown(support, False).status_code == 200
    assert mine(support)["showAmount"] is False and board(support) == [(2, None)]
    assert shown(support, True, consent=donations.CONSENT).status_code == 400
    assert shown(support, "yes").status_code == 400
    assert shown(support, True).status_code == 200 and board(support) == [(2, 5107)]
    # a second donor, shown by default: a smaller total sorts below; a hidden total after the shown ones of its tier
    bek = upload(support, monkeypatch, fields(clock[0], amount=2500, no="222222222222222222"), tg=8, shade=120)["receipts"][0]["id"]
    assert decide(support, bek, "confirm", 2500).status_code == 204
    assert board(support) == [(2, 5107), (1, 2500)]
    assert shown(support, False, tg=8).status_code == 200 and board(support) == [(2, 5107), (1, None)]
    # a stale show loses; a hide always wins
    rev = mine(support)["rev"]
    assert shown(support, False, rev=None, consent="old").status_code == 200
    assert shown(support, True, rev=rev).status_code == 409
    assert board(support) == [(2, None), (1, None)]
    assert shown(support, True).status_code == 200
    # hiding the name hides the amount; showing the name again never brings the figure back by itself
    assert consent(support, False).status_code == 200 and board(support) == [(1, None)]
    assert shown(support, True).status_code == 409  # no figure beside nobody
    assert consent(support, True).status_code == 200
    assert mine(support)["showAmount"] is False and board(support) == [(2, None), (1, None)]
    assert con.execute("SELECT amount FROM sponsor_consents WHERE user_id = ? ORDER BY id DESC", (ids[8],)).fetchone()[0] is None


def test_consent_does_not_follow_a_telegram_account_change(support, monkeypatch):
    c, _, con, ids, clock = support
    upload(support, monkeypatch, fields(clock[0]))
    assert consent(support, True).status_code == 200
    con.execute("UPDATE users SET tg_id = 700 WHERE id = ?", (ids[7],))
    assert c.get("/api/sponsors", headers=tma(8)).json() == []


def test_upload_requires_receipt_consent_and_enabled_destination_before_reading(support, monkeypatch):
    c, cfg, _, _, _ = support
    def unexpected(im):
        raise AssertionError("read without consent")
    monkeypatch.setattr(receipt, "read", unexpected)
    for suffix in ("", "?consent=old"):
        assert c.post("/api/donate/receipt" + suffix, headers=tma(7), content=_shot()).status_code == 403
    off = TestClient(server.create(dataclasses.replace(cfg, donate_phone="")))
    assert off.post("/api/donate/receipt?consent=dn2", headers=tma(7), content=_shot()).status_code == 404


def test_five_per_rolling_day_even_after_decisions(support, monkeypatch):
    c, _, _, _, clock = support
    for i in range(5):
        did = upload(support, monkeypatch, {}, shade=200 + i)["receipts"][0]["id"]
        assert decide(support, did, "reject").status_code == 204
    r = c.post("/api/donate/receipt?consent=dn2", headers=tma(7), content=_shot())
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
    clock[0] += 86401
    assert upload(support, monkeypatch, {})["receipts"][0]["status"] == "pending"


def test_failed_uploads_share_the_event_processing_limit(support, monkeypatch):
    c, _, con, ids, _ = support
    attempts = []
    def bad(*args):
        attempts.append(True)
        raise media.BadImage("invalid")
    monkeypatch.setattr(receipt, "take", bad)
    for _ in range(logic.core.UPLOAD_LIMIT["receipt"]):
        assert c.post("/api/donate/receipt?consent=dn2", headers=tma(7), content=b"bad").status_code == 400
    assert c.post("/api/donate/receipt?consent=dn2", headers=tma(7), content=b"bad").status_code == 429
    assert len(attempts) == logic.core.UPLOAD_LIMIT["receipt"]
    assert con.execute("SELECT value FROM meta WHERE key = ?", (f"upload:{ids[7]}:receipt",)).fetchone()
    assert mine(support)["receipts"] == []


@pytest.mark.parametrize("same_file", [False, True])
def test_parallel_uploads_cannot_exceed_the_row_cap_or_erase_the_winners_image(support, monkeypatch, same_file):
    c, _, con, _, _ = support
    for i in range(4):
        upload(support, monkeypatch, {}, shade=200 + i)
    barrier = Barrier(2)
    def read(im):
        barrier.wait(timeout=10)
        return {}
    monkeypatch.setattr(receipt, "read", read)
    def send(shade):
        return c.post("/api/donate/receipt?consent=dn2", headers=tma(7), content=_shot(shade)).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(send, [210, 210 if same_file else 211])) == [200, 429]
    assert con.execute("SELECT COUNT(*) FROM donations").fetchone()[0] == 5
    assert con.execute("SELECT COUNT(*) FROM files WHERE kind = 'receipt'").fetchone()[0] == 5
    for r in mine(support)["receipts"]:
        assert c.get(f"/api/donate/receipts/{r['id']}/image", headers=tma(7)).status_code == 200


def test_ban_during_ocr_prevents_persistence(support, monkeypatch):
    c, cfg, con, ids, clock = support
    def ban(im):
        con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (ids[7],))
        return fields(clock[0])
    monkeypatch.setattr(receipt, "read", ban)
    assert c.post("/api/donate/receipt?consent=dn2", headers=tma(7), content=_shot()).status_code == 403
    assert not con.execute("SELECT 1 FROM donations").fetchone()
    assert not list((Path(cfg.db_path).parent / "receipts").rglob("*.webp"))


def test_retention_deletes_all_image_variants_and_keeps_the_total_and_reuse_guard(support, monkeypatch):
    c, cfg, con, _, clock = support
    got = upload(support, monkeypatch, fields(clock[0]))
    did = got["receipts"][0]["id"]
    root = Path(cfg.db_path).parent / "receipts"
    clock[0] += donations.KEEP - 1
    assert decide(support, did, "confirm", 3000).status_code == 204
    donations.sweep(con)
    assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(7)).status_code == 200
    clock[0] += 1
    assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(7)).status_code == 404
    donations.sweep(con)
    assert not list(root.rglob("*.*"))
    assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(7)).status_code == 404
    d = con.execute("SELECT * FROM donations WHERE id = ?", (did,)).fetchone()
    assert all(d[k] is None for k in ("file_id", "recipient_name", "sender_name", "paid_at", "undo"))
    assert d["receipt_no"] and d["sha256"] and d["amount"] == 3000
    assert mine(support)["total"] == 3000
    assert decide(support, did, "reject").status_code == 409
    reused = upload(support, monkeypatch, fields(clock[0]), shade=241)
    assert reused["receipts"][0]["status"] == "pending" and reused["total"] == 3000


def test_untracked_receipt_files_are_purged_after_an_interrupted_upload(support):
    _, cfg, con, _, clock = support
    root = Path(cfg.db_path).parent / "receipts"
    receipt.take(_shot(), root, b"orphan")
    files = list(root.rglob("*.*"))
    assert len(files) == 3
    donations.sweep(con)
    assert all(f.exists() for f in files)
    old = clock[0] - 86401
    for f in files:
        os.utime(f, (old, old))
    donations.sweep(con)
    assert not any(f.exists() for f in files)


def test_pending_receipts_expire_without_a_medal(support, monkeypatch):
    c, cfg, con, _, clock = support
    did = upload(support, monkeypatch, {})["receipts"][0]["id"]
    clock[0] += donations.PENDING_KEEP
    donations.sweep(con)
    assert mine(support)["receipts"][0]["status"] == "rejected" and mine(support)["tier"] == 0
    assert not list((Path(cfg.db_path).parent / "receipts").rglob("*.*"))
    assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(7)).status_code == 404


def test_rejected_receipt_expires_thirty_days_after_the_decision(support, monkeypatch):
    c, _, con, _, clock = support
    did = upload(support, monkeypatch, {})["receipts"][0]["id"]
    clock[0] += 86400
    assert decide(support, did, "reject").status_code == 204
    clock[0] += donations.KEEP - 1
    donations.sweep(con)
    assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(7)).status_code == 200
    clock[0] += 1
    donations.sweep(con)
    assert c.get(f"/api/donate/receipts/{did}/image", headers=tma(7)).status_code == 404
    assert mine(support)["total"] == 0


def test_public_photo_does_not_keep_a_private_receipt_forever(support, monkeypatch):
    _, cfg, con, ids, clock = support
    upload(support, monkeypatch, fields(clock[0]))
    con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at)
        SELECT sha256, 'avatar', mime, bytes, width, height, path, ?, created_at FROM files WHERE kind = 'receipt'""", (ids[8],))
    clock[0] += donations.KEEP
    donations.sweep(con)
    assert not list((Path(cfg.db_path).parent / "receipts").rglob("*.*"))
    assert con.execute("SELECT 1 FROM files WHERE kind = 'avatar'").fetchone()


def test_identical_uploads_keep_independent_private_files_and_retention(support, monkeypatch):
    c, cfg, con, _, clock = support
    first = upload(support, monkeypatch, fields(clock[0]))["receipts"][0]["id"]
    second = upload(support, monkeypatch, fields(clock[0]), tg=8)["receipts"][0]["id"]
    files = con.execute("SELECT path, sha256 FROM files WHERE kind = 'receipt'").fetchall()
    assert len(files) == 2 and files[0]["path"] != files[1]["path"] and files[0]["sha256"] == files[1]["sha256"]
    clock[0] += donations.KEEP
    donations.sweep(con)
    assert c.get(f"/api/donate/receipts/{first}/image", headers=tma(7)).status_code == 404
    assert c.get(f"/api/donate/receipts/{second}/image", headers=tma(8)).status_code == 200
    clock[0] += donations.PENDING_KEEP
    donations.sweep(con)
    assert not list((Path(cfg.db_path).parent / "receipts").rglob("*.*"))


def test_account_deletion_removes_receipts_donations_consent_and_medal_but_not_replay_guard(support, monkeypatch):
    c, cfg, con, ids, clock = support
    upload(support, monkeypatch, fields(clock[0]))
    hear(cfg, Telegram([payment(charge="erase")], []))
    assert consent(support, True).status_code == 200
    # The same bytes in public media must not retain the private copy after account deletion.
    con.execute("""INSERT INTO files (sha256, kind, mime, bytes, width, height, path, owner_id, created_at)
        SELECT sha256, 'avatar', mime, bytes, width, height, path, ?, created_at FROM files WHERE kind = 'receipt'""", (ids[8],))
    delete_now(c, cfg, tma(7))
    for table in ("donations", "sponsor_consents", "achievement_grants", "achievement_levels", "bot_outbox"):
        assert not con.execute(f"SELECT 1 FROM {table} WHERE user_id = ?", (ids[7],)).fetchone(), table
    assert not list((Path(cfg.db_path).parent / "receipts").rglob("*.*"))
    assert c.get("/api/sponsors", headers=tma(8)).json() == []
    assert con.execute("SELECT 1 FROM star_gifts WHERE charge_id = 'erase'").fetchone()
    hear(cfg, Telegram([payment(charge="erase")], []))
    assert not con.execute("SELECT 1 FROM donations").fetchone()


def test_bot_uses_only_localized_templates_and_suppresses_stale_decisions(support, monkeypatch):
    _, _, con, ids, _ = support
    did = upload(support, monkeypatch, {"amount": 2000})["receipts"][0]["id"]
    assert decide(support, did, "confirm", 2000).status_code == 204
    for lang in ("ru", "kk", "en"):
        con.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, ids[7]))
        row = con.execute("SELECT b.*, ? AS lang FROM bot_outbox b WHERE kind = 'donation_confirmed'", (lang,)).fetchone()
        assert outbox._render(con, row) == (*texts.bot_message(lang, "donation_confirmed"), "donate")
    assert decide(support, did, "reject").status_code == 204
    assert outbox._render(con, row) is None
    rejected = con.execute("SELECT b.*, 'en' AS lang FROM bot_outbox b WHERE kind = 'donation_rejected'").fetchone()
    assert outbox._render(con, rejected) == (*texts.bot_message("en", "donation_rejected"), "donate")
    assert decide(support, did, "undo").status_code == 204
    assert outbox._render(con, rejected) is None


def test_admin_donation_add_by_hand_grants_the_medal_shown_by_default(support, monkeypatch, capsys):
    """`admin donation add`: a confirmed manual row and the medal; shown unless hidden; no twin that day without --again;
    unknown people and silly amounts refused; `donation list` names nobody."""
    c, cfg, con, ids, clock = support
    monkeypatch.setattr(admin.config, "load", lambda: cfg)
    admin.main(["donation", "add", "7", "6000", "2026-11-20"])
    assert capsys.readouterr().out.strip().endswith("tier 2, public")
    assert mine(support)["tier"] == 2 and board(support) == [(2, 6000)]
    for bad in (["donation", "add", "7", "6000", "2026-11-20"], ["donation", "add", "999", "100"],
                ["donation", "add", "7", "0"], ["donation", "add", "7", "10000001"]):
        with pytest.raises(SystemExit):
            admin.main(bad)
    admin.main(["donation", "add", "7", "6000", "2026-11-20", "--again"])
    assert mine(support)["total"] == 12000
    assert con.execute("SELECT COUNT(*) FROM donations WHERE flags = 'manual' AND status = 'confirmed'").fetchone()[0] == 2
    capsys.readouterr()
    admin.main(["donation", "list"])
    out = capsys.readouterr().out
    assert out.count("manual") == 2 and "2026-11-20" in out and "public yes" in out and "Aidar" not in out
    assert f"user {ids[7]}" in out and "tg 7" not in out
    for did, in con.execute("SELECT id FROM donations WHERE flags = 'manual'").fetchall():
        admin.main(["donation", "remove", str(did)])
    assert mine(support)["tier"] == 0 and mine(support)["total"] == 0
    assert not con.execute("SELECT 1 FROM achievement_levels WHERE user_id = ? AND code = 'sponsor'", (ids[7],)).fetchone()
    with pytest.raises(SystemExit):
        admin.main(["donation", "remove", str(did)])
