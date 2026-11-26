"""The Apple Wallet pass (kbtu/wallet.py): one per person, the badge QR the door already takes, behind a link only /api/me
gives its owner. Signed here with a throwaway self-signed certificate (Apple's own is the owner's, in the env)."""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from kbtu import app as server, db, logic, wallet
from test_core import env, login, tma  # noqa: F401 - env is a fixture


def _cert(cn: str) -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return cert.public_bytes(serialization.Encoding.PEM).decode(), pem.decode()


@pytest.fixture
def on(env):  # noqa: F811
    _, cfg = env
    shutil.copy(Path(__file__).parents[2] / "web/public/apple-touch-icon.png", Path(cfg.web_dist) / "apple-touch-icon.png")
    cert, key = _cert("Pass Type ID: pass.test.badge")
    wwdr, _ = _cert("WWDR")
    cfg = dataclasses.replace(cfg, wallet_cert=cert + wwdr, wallet_key=key.replace("\n", "\\n"),  # escaped, as an env line has it
                              wallet_type_id="pass.test.badge", apple_team_id="TEAM123456")
    return TestClient(server.create(cfg)), cfg


def test_off_without_certificate(env):  # noqa: F811
    c, cfg = env
    me = login(c, 10, "ali")
    assert "wallet" not in c.get("/api/me", headers=tma(10)).json()
    assert c.get(f"/wallet/{me['id']}-x.pkpass").status_code == 404
    # half set, or a key that isn't the certificate's: off, never a crash
    assert wallet.signer(dataclasses.replace(cfg, wallet_type_id="pass.x")) is None
    cert, _ = _cert("a")
    _, other = _cert("b")
    assert wallet.signer(dataclasses.replace(cfg, wallet_cert=cert, wallet_key=other, wallet_type_id="pass.x", apple_team_id="T")) is None


def test_pass_is_the_badge(on):
    c, cfg = on
    assert "wallet" not in c.get("/api/me", headers=tma(9, "Guest")).json()   # no student: no badge, no pass
    me = login(c, 10, "ali")
    url = me["wallet"]
    assert url.startswith(f"https://{cfg.domain}/wallet/{me['id']}-") and url.endswith(".pkpass")
    path = url.removeprefix(f"https://{cfg.domain}")
    r = c.get(path)                                                           # no Telegram: Safari has no session
    assert r.status_code == 200 and r.headers["content-type"] == "application/vnd.apple.pkpass"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    p = json.loads(z.read("pass.json"))
    # the very QR the profile shows, which the door's scanner takes (PROFILE_QR), for this person only
    msg = p["barcodes"][0]["message"]
    assert msg == f"https://t.me/{cfg.bot_username}?startapp=u_{me['qr']}"
    m = logic.PROFILE_QR.search(msg)
    assert m and int(m[1]) == me["id"]
    assert p["passTypeIdentifier"] == "pass.test.badge" and p["teamIdentifier"] == "TEAM123456" and p["sharingProhibited"] is True
    assert p["generic"]["primaryFields"][0]["value"] == "Ali Testov"
    manifest = json.loads(z.read("manifest.json"))
    assert set(manifest) == set(z.namelist()) - {"manifest.json", "signature"} and {"icon.png", "icon@2x.png", "logo.png"} <= set(manifest)
    assert all(hashlib.sha1(z.read(n)).hexdigest() == h for n, h in manifest.items())
    assert z.read("signature")[:1] == b"\x30"                                 # DER

    # another link fails: a changed key, my key on someone else, a made-up one
    other = login(c, 11, "bob")
    sig = path.split("-", 1)[1].removesuffix(".pkpass")
    assert c.get(path.replace(sig, sig[:-1] + ("A" if sig[-1] != "A" else "B"))).status_code == 404
    assert c.get(f"/wallet/{other['id']}-{sig}.pkpass").status_code == 404

    # the link dies with the badge's code (a deleted account wipes it) and with a ban, as the door's badge does
    con = db.connect(cfg.db_path)
    with db.tx(con):
        con.execute("UPDATE users SET banned_at = 1 WHERE id = ?", (me["id"],))
    assert c.get(path).status_code == 404
    with db.tx(con):
        con.execute("UPDATE users SET banned_at = NULL, qr_code = NULL WHERE id = ?", (me["id"],))
    assert c.get(path).status_code == 404
    con.close()
    assert c.get("/api/me", headers=tma(10)).json()["wallet"] != url          # a new code, a new link
