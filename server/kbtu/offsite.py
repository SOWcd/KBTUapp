"""The off-site copy (PLAN item 22): the nightly database copy and the receipts, and on Sundays the media too, packed
with tar, encrypted with age to the owner's public key (the private one stays offline with him: this server can write
backups but never read them) and put into R2 bucket kbtu-app-backups with one SigV4 PUT. The bucket keeps each object
29 days locked and deletes it at 30. Off until Coolify has the four BACKUP_* settings and the image has `age`."""
from __future__ import annotations

import datetime
import hashlib
import hmac
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx

BUCKET = "kbtu-app-backups"
KEYS = ("BACKUP_S3_ENDPOINT", "BACKUP_S3_KEY", "BACKUP_S3_SECRET", "BACKUP_AGE_RECIPIENT")


def ready() -> bool:
    return all(os.environ.get(k) for k in KEYS) and shutil.which("age") is not None


def sign(method: str, url: str, headers: dict[str, str], key: str, secret: str, region: str, amz: str) -> str:
    """AWS Signature V4's Authorization header (R2's region is "auto"); `headers` are all signed, x-amz-date among them"""
    u, day = urlsplit(url), amz[:8]
    h = {k.lower(): v.strip() for k, v in {**headers, "host": u.netloc}.items()}
    names = ";".join(sorted(h))
    canon = "\n".join([method, u.path or "/", u.query, *(f"{k}:{h[k]}" for k in sorted(h)), "", names, h["x-amz-content-sha256"]])
    scope = f"{day}/{region}/s3/aws4_request"
    todo = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canon.encode()).hexdigest()])
    k = ("AWS4" + secret).encode()
    for part in (day, region, "s3", "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    return f"AWS4-HMAC-SHA256 Credential={key}/{scope}, SignedHeaders={names}, Signature={hmac.new(k, todo.encode(), hashlib.sha256).hexdigest()}"


def upload(paths: list[Path], name: str, work: Path) -> int:
    """tar `paths` (files and whole folders) | age -> a temp file in `work` -> PUT as `name`; its size"""
    env = os.environ
    with tempfile.NamedTemporaryFile(dir=work, suffix=".age") as out:
        age = subprocess.Popen(["age", "-r", env["BACKUP_AGE_RECIPIENT"], "-o", out.name], stdin=subprocess.PIPE)
        with tarfile.open(fileobj=age.stdin, mode="w|") as tar:
            for p in paths:
                if p.exists():
                    tar.add(p, arcname=p.name)
        age.stdin.close()
        if age.wait():
            raise RuntimeError(f"age exited {age.returncode}")
        size = os.path.getsize(out.name)
        url = f"{env['BACKUP_S3_ENDPOINT'].rstrip('/')}/{BUCKET}/{name}"
        h = {"x-amz-content-sha256": "UNSIGNED-PAYLOAD", "x-amz-date": datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")}
        h["authorization"] = sign("PUT", url, h, env["BACKUP_S3_KEY"], env["BACKUP_S3_SECRET"], "auto", h["x-amz-date"])
        with open(out.name, "rb") as f:
            r = httpx.put(url, content=f, headers={**h, "content-length": str(size)}, timeout=httpx.Timeout(60, write=3600))
        if r.status_code != 200:
            raise RuntimeError(f"R2 {r.status_code}: {r.text[:200]}")
        return size
