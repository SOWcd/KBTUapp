"""Apple Wallet: one pass per person, their badge QR (§4.4) that every event's door scanner already takes
(organizing.checkin's PROFILE_QR). Added once, never changes: no web service, no push updates. The pass carries the
same link the profile's QR shows, so it lets in exactly whom the badge lets in, and stops working with it (the code
is wiped with the account). Signing needs a Pass Type ID certificate (README "Feature switches"); without one: off."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import zipfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from PIL import Image

from . import texts
from .logic.core import one


def _pem(raw: str) -> bytes:
    """An env value: the PEM itself (real or escaped newlines), a path to it, or its base64."""
    raw = raw.strip()
    if "-----BEGIN" in raw:
        return raw.replace("\\n", "\n").encode()
    if raw.startswith("/") and Path(raw).is_file():
        return Path(raw).read_bytes()
    return base64.b64decode(raw)


class Signer:
    """The certificate chain (the pass certificate first, then Apple's WWDR intermediate) and its key, read once."""

    def __init__(self, cert: str, key: str, type_id: str, team_id: str, icon: Path):
        self.certs = x509.load_pem_x509_certificates(_pem(cert))
        self.key = serialization.load_pem_private_key(_pem(key), password=None)
        pub = serialization.PublicFormat.SubjectPublicKeyInfo
        if self.key.public_key().public_bytes(serialization.Encoding.DER, pub) != self.certs[0].public_key().public_bytes(serialization.Encoding.DER, pub):
            raise ValueError("WALLET_PASS_KEY is not the key of WALLET_PASS_CERT's first certificate")
        self.type_id, self.team_id = type_id, team_id
        src = Image.open(icon).convert("RGBA")
        self.images = {}  # the app's icon at Wallet's sizes (icon 29 pt, logo 50 pt; 1x to 3x), made once
        for name, pt in (("icon", 29), ("logo", 50)):
            for k in (1, 2, 3):
                buf = io.BytesIO()
                src.resize((pt * k, pt * k), Image.LANCZOS).save(buf, "PNG")
                self.images[f"{name}{'' if k == 1 else f'@{k}x'}.png"] = buf.getvalue()

    def sign(self, manifest: bytes) -> bytes:
        b = pkcs7.PKCS7SignatureBuilder().set_data(manifest).add_signer(self.certs[0], self.key, hashes.SHA256())
        for c in self.certs[1:]:
            b = b.add_certificate(c)
        return b.sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])


def signer(cfg) -> Signer | None:
    """The four settings, all set and valid, or off (a bad one is said once at start, never its value)."""
    vals = (cfg.wallet_cert, cfg.wallet_key, cfg.wallet_type_id, cfg.apple_team_id)
    if not all(vals):
        if any(vals):
            print("Apple Wallet: WALLET_PASS_CERT, WALLET_PASS_KEY, WALLET_PASS_TYPE_ID and APPLE_TEAM_ID go together: off", flush=True)
        return None
    try:
        return Signer(*vals, Path(cfg.web_dist) / "apple-touch-icon.png")
    except Exception as e:  # noqa: BLE001 - a broken certificate turns the feature off, never the app
        print(f"Apple Wallet: off ({type(e).__name__})", flush=True)
        return None


def _sig(key: bytes, uid: int, code: str) -> str:
    """The download link's key: bound to the badge's code, so a link dies with the code (a deleted account)."""
    return base64.urlsafe_b64encode(hmac.new(key, f"kbtu-wallet:{uid}:{code}".encode(), hashlib.sha256).digest()[:18]).decode()


def link(cfg, con, uid: int) -> str | None:
    """My pass's link for /api/me (opened in the phone's browser, which has no session): it gives exactly what /api/me
    already gives me, my badge QR. None for whoever has no badge the door takes."""
    u = one(con, """SELECT u.qr_code FROM users u JOIN students s ON s.user_id = u.id
        WHERE u.id = ? AND s.manual = 0 AND u.banned_at IS NULL""", uid)
    return f"https://{cfg.domain}/wallet/{uid}-{_sig(cfg.token_key, uid, u['qr_code'])}.pkpass" if u and u["qr_code"] else None


def build(cfg, s: Signer, con, uid: int, sig: str) -> bytes | None:
    """The signed .pkpass, or None: a wrong or stale link, no badge the door takes (the same rule as the door's)."""
    u = one(con, """SELECT u.qr_code, u.card_no, u.is_founder, u.lang, s.first_name, s.last_name FROM users u JOIN students s ON s.user_id = u.id
        WHERE u.id = ? AND s.manual = 0 AND u.banned_at IS NULL AND u.qr_code IS NOT NULL""", uid)
    if not u or not hmac.compare_digest(sig.encode(), _sig(cfg.token_key, uid, u["qr_code"]).encode()):
        return None
    w = texts.pick(texts.WALLET, u["lang"])
    no = 0 if u["is_founder"] else u["card_no"]
    pass_json = {
        "formatVersion": 1, "passTypeIdentifier": s.type_id, "teamIdentifier": s.team_id,
        "serialNumber": f"badge-{uid}",  # one per person: adding it again replaces it
        "organizationName": "KBTU App", "description": w["description"], "logoText": "KBTU App",
        "foregroundColor": "rgb(255, 255, 255)", "labelColor": "rgb(169, 192, 255)", "backgroundColor": "rgb(18, 26, 61)",
        "sharingProhibited": True,  # it is its holder's way in: Wallet offers no Share
        "generic": {
            "primaryFields": [{"key": "name", "label": w["name"], "value": f"{u['first_name']} {u['last_name'] or ''}".strip()}],
            "secondaryFields": [{"key": "no", "label": w["no"], "value": f"#{no}"}] if no is not None else [],
            "backFields": [{"key": "how", "label": w["howLabel"], "value": w["how"]}],
        },
        # the very link the profile's QR shows (Hero.svelte): the door reads u_<id>_<code> from it
        "barcodes": [{"format": "PKBarcodeFormatQR", "message": f"https://t.me/{cfg.bot_username}?startapp=u_{uid}_{u['qr_code']}",
                      "messageEncoding": "iso-8859-1"}],
    }
    files = {"pass.json": json.dumps(pass_json, ensure_ascii=False).encode(), **s.images}
    manifest = json.dumps({n: hashlib.sha1(b).hexdigest() for n, b in files.items()}).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in {**files, "manifest.json": manifest, "signature": s.sign(manifest)}.items():
            z.writestr(n, b)
    return out.getvalue()
