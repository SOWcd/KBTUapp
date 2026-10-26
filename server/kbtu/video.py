"""Event videos: a club adds a short vertical video to an event right in the editor; the Feed plays it.

The phone sends the file as it is, in 8 MB pieces (Cloudflare refuses a request over 100 MB, and a piece lost on a
bad connection is sent again, not the whole file); the postman's process compresses one video at a time. What we
keep is only our own copy: H.264 (every phone and Telegram's webviews play it; HEVC and AV1 don't play everywhere),
at most 720 px wide, 30 frames a second, CRF 26 with a 2.5 Mbit/s cap, AAC 96 kbit/s, the index at the front so it
starts before it has loaded. Measured Oct 14 on a 1080x1920 60 fps reel: 15 s -> 1.6 MB (an Instagram reel of the
same length is ~2 MB); CRF 23 was 30 % bigger for a VMAF 1 point higher, CRF 28 20 % smaller for 1 point lower.
iPhones film in HDR (HLG, Dolby Vision); played as SDR it looks grey and washed out, so HDR is tone-mapped. Metadata
(the GPS spot where it was filmed, the phone, the date) never makes it into our copy, and the original is deleted.

ffmpeg reads untrusted files: only the containers phones and editors write, and only local files (an uploaded
playlist could otherwise make ffmpeg fetch addresses or read files on the server)."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from . import media

log = logging.getLogger("kbtu.video")

MAX_BYTES = 500 * 1024 * 1024   # a minute of 4K from an iPhone is ~400 MB
PIECE = 8 * 1024 * 1024         # the client's piece; the server takes up to twice that
MAX_SECONDS = 60
WIDE_SECONDS = 20
FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm"   # ffmpeg's names: what phones and video editors write
SAFE_IN = ["-protocol_whitelist", "file", "-format_whitelist", FORMATS]
HDR = {"smpte2084", "arib-std-b67"}   # PQ (Dolby Vision, HDR10) and HLG


class BadVideo(ValueError):
    pass


async def _run(*cmd: str, timeout: int = 900) -> bytes:
    p = await asyncio.create_subprocess_exec("nice", "-n", "10", *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(p.communicate(), timeout)
    except TimeoutError:
        p.kill()
        raise BadVideo("timeout") from None
    if p.returncode:
        raise BadVideo(err.decode(errors="replace")[-300:])
    return out


async def probe(src: Path, wide: bool = False) -> dict:
    """The first video stream and the length; anything that isn't a video of 1-60 s is BadVideo (the wide slot takes a
    longer one and keeps its first 20 s)."""
    raw = await _run("ffprobe", "-v", "error", *SAFE_IN, "-show_entries",
                     "stream=codec_type,width,color_transfer:format=duration", "-of", "json", str(src), timeout=60)
    info = json.loads(raw)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    try:
        dur = float(info["format"]["duration"])
    except (KeyError, ValueError):
        dur = 0
    if not v or not v.get("width") or not 1 <= dur <= (1e6 if wide else MAX_SECONDS + 1):
        raise BadVideo("too_long" if dur > MAX_SECONDS + 1 else "not_a_video")
    return {"duration": dur, "hdr": v.get("color_transfer") in HDR, "transfer": v.get("color_transfer")}


def args(src: Path, dst: Path, info: dict) -> list[str]:
    # 720 on the short side, whichever way the clip stands (ffmpeg has turned it upright by now; probe's width hasn't)
    fit = ("scale=w='if(gt(iw,ih),min(1280,iw),min(720,iw))':h='if(gt(iw,ih),min(720,ih),min(1280,ih))'"
           ":force_original_aspect_ratio=decrease:force_divisible_by=2")
    # the wide slot plays muted behind the event's sheet in a loop: no sound, 20 s, a lower cap (PLAN 32: data cost)
    wide = info.get("wide")
    sound = ["-an"] if wide else ["-c:a", "aac", "-b:a", "96k", "-ac", "2"]
    # HDR to SDR: to linear light, BT.709 primaries, Hable's curve, back to BT.709 (zimg; the input's own transfer named,
    # as phones don't always tag primaries and matrix)
    tone = (f"zscale=tin={info['transfer']}:pin=bt2020:min=bt2020nc:t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,") if info["hdr"] else ""
    return ["ffmpeg", "-v", "error", "-y", *SAFE_IN, "-i", str(src),
            "-map", "0:v:0", *([] if wide else ["-map", "0:a:0?"]), "-map_metadata", "-1", "-map_chapters", "-1", "-sn", "-dn",
            "-vf", f"{tone}format=yuv420p,{fit}", "-fpsmax", "30",
            "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-maxrate", "1500k" if wide else "2500k", "-bufsize", "5000k", "-profile:v", "high",
            "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            *sound, "-t", str(WIDE_SECONDS if wide else MAX_SECONDS), "-fs", "60M", "-threads", "3",
            "-movflags", "+faststart", str(dst)]


async def compress(src: Path, root: Path, wide: bool = False) -> dict:
    """The upload at src becomes root/<2 hex>/<sha256>.mp4 with its poster as a photo of the same name (media.store:
    .webp, .t.webp, .jpg); returns what the videos table keeps. The original stays where it is (the caller deletes it)."""
    info = {**await probe(src, wide), "wide": wide}
    tmp = src.with_suffix(".out.mp4")
    try:
        await _run(*args(src, tmp, info))
        data = tmp.read_bytes()
        frame = await _run("ffmpeg", "-v", "error", "-ss", str(min(1.0, info["duration"] / 3)), "-i", str(tmp),
                           "-frames:v", "1", "-f", "image2", "-c:v", "png", "-", timeout=60)
        im = await asyncio.to_thread(media.decode, frame)
        saved = await asyncio.to_thread(media.store, im, data, root)
        shutil.move(tmp, root / f"{saved['path']}.mp4")
    finally:
        tmp.unlink(missing_ok=True)
    return {"path": saved["path"], "width": saved["width"], "height": saved["height"], "color": saved["color"],
            "duration": round(info["duration"], 1), "bytes": len(data)}
