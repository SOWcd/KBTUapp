"""Public forms: our own Google Forms. Anyone opens kbtu.sow.kz/f/<slug> in any browser, with no account, and
answers; the answers stay in our database. A form is a JSON spec made by hand (`admin form new`, no builder):

  {"title", "intro", "thanks", "lang": "ru" | "kk" | "en",
   "research"?: true, "about"?: "one line for the Forum research list",
   "sections": [{"title", "questions": [{"id", "type": "text" | "long" | "choice" | "multi" | "scale", "label",
                 "hint"?, "options"? (choice, multi), "other"?: bool (choice, multi: a free line of their own),
                 "low"?, "high"? (scale: what 1 and 5 mean), "required"?: bool}]}]}

Public answers are anonymous. Research forms use the verified, signed-by-default app flow in research.py. The page is one HTML
response with its CSS and a small script inline, so it opens at once anywhere; its colours, radii and sizes are
copied from web/src/ui/tokens.css (a separate page: it can't import them)."""
from __future__ import annotations

import csv
import html
import io
import json
import re
import time

from ..db import tx
from .. import texts
from ..calpage import _sha
from . import core
from .core import ApiError, one, rows

A_DAY = 500          # answers a form takes in a day, from everyone: a flood can't fill the disk
KEEP = 365 * 86400   # at most one year after closing
LONG, SHORT = 4000, 200
MOST = 1 << 20       # an answer sheet's bytes: far above a real one; no account guards the route, so it's capped unread
OTHER = "__other__"  # the "Other" chip's value; its words come in the field "<id>~"
TYPES = ("text", "long", "choice", "multi", "scale")
SCALE = ("1", "2", "3", "4", "5")
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")
_QID = re.compile(r"[a-z0-9_]{1,32}")
# control and bidi characters out (answers are printed in the admin's terminal and opened in a spreadsheet); a long
# answer keeps its line breaks
_CTRL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\ud800-\udfff]")


def _line(x: object, most: int) -> str:
    return " ".join(_CTRL.sub(" ", x).split())[:most] if isinstance(x, str) else ""


def _text(x: object, most: int) -> str:
    return _CTRL.sub(" ", x.replace("\r", "")).strip()[:most] if isinstance(x, str) else ""


def check_spec(spec: object) -> dict:
    """The spec as stored: known keys only, sizes and types checked. ApiError("bad_input", why) names the first flaw."""
    def bad(why: str):
        raise ApiError("bad_input", why)
    if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list):
        bad("spec: an object with sections")
    out = {"title": _line(spec.get("title"), 120), "intro": _text(spec.get("intro"), 1200), "thanks": _text(spec.get("thanks"), 600),
           "lang": spec.get("lang", "ru"), "sections": []}
    if not out["title"] or out["lang"] not in texts.FORM_PAGE or not 1 <= len(spec["sections"]) <= 20:
        bad("title, lang (ru, kk, en) and 1 to 20 sections")
    seen: set[str] = set()
    for s in spec["sections"]:
        if not isinstance(s, dict) or not isinstance(s.get("questions"), list) or not 1 <= len(s["questions"]) <= 30:
            bad("a section: 1 to 30 questions")
        qs = []
        for q in s["questions"]:
            qid = q.get("id") if isinstance(q, dict) else None
            if not isinstance(qid, str) or not _QID.fullmatch(qid) or qid in seen or qid == "website":
                bad(f"question id {qid!r}: unique, a-z 0-9 _, up to 32")
            seen.add(qid)
            c = {"id": qid, "type": q.get("type"), "label": _line(q.get("label"), 300)}
            if c["type"] not in TYPES or not c["label"]:
                bad(f"{qid}: a type ({', '.join(TYPES)}) and a label")
            if hint := _line(q.get("hint"), 300):
                c["hint"] = hint
            if q.get("required") is True:
                c["required"] = True
            if c["type"] in ("choice", "multi"):
                opts = [_line(o, 120) for o in q["options"]] if isinstance(q.get("options"), list) else []
                if not 2 <= len(opts) <= 30 or "" in opts or OTHER in opts or len(set(opts)) != len(opts):
                    bad(f"{qid}: 2 to 30 different options")
                c["options"] = opts
                if q.get("other") is True:
                    c["other"] = True
            if c["type"] == "scale":
                c |= {k: v for k in ("low", "high") if (v := _line(q.get(k), 40))}
            qs.append(c)
        out["sections"].append({"title": _line(s.get("title"), 120), "questions": qs})
    return out


def create(con, slug: str, spec: object) -> int:
    if not _SLUG.fullmatch(slug):
        raise ApiError("bad_input", "slug: a-z 0-9 -, 2 to 40")
    checked = check_spec(spec)
    if type(spec.get("research", False)) is not bool:
        raise ApiError("bad_input", "research: true or false")
    about = _line(spec.get("about"), 200) if spec.get("research") else ""
    if spec.get("research") and not about:
        raise ApiError("bad_input", "research: about required")
    body = json.dumps(checked, ensure_ascii=False)
    with tx(con):
        if one(con, "SELECT 1 FROM forms WHERE slug = ?", slug):
            raise ApiError("conflict", "slug taken")
        fid = con.execute("INSERT INTO forms (slug, spec, created_at) VALUES (?, ?, ?)", (slug, body, core.now())).lastrowid
        if about:
            con.execute("INSERT INTO research_forms (form_id, about) VALUES (?, ?)", (fid, about))
        return fid


def close(con, slug: str) -> None:
    if not con.execute("UPDATE forms SET closed_at = ? WHERE slug = ? AND closed_at IS NULL", (core.now(), slug)).rowcount:
        raise ApiError("not_found")


def _questions(spec: dict) -> list[dict]:
    return [q for s in spec["sections"] for q in s["questions"]]


def answers(spec: dict, body: object) -> dict:
    """Shared answer validation for public forms and the native research sheet."""
    if not isinstance(body, dict):
        raise ApiError("bad_input")
    out: dict[str, str | list[str]] = {}
    for q in _questions(spec):
        got, kind = body.get(q["id"]), q["type"]
        vals = [x for x in (got if isinstance(got, list) else [got])[:40] if isinstance(x, str)]
        if kind in ("text", "long"):
            v = (_line(vals[0], SHORT) if kind == "text" else _text(vals[0], LONG)) if vals else ""
        elif kind == "scale":
            v = vals[0] if vals else ""
            if v and v not in SCALE:
                raise ApiError("bad_input", q["id"])
        else:
            other, picked = body.get(q["id"] + "~"), []
            for x in dict.fromkeys(vals):
                if x == OTHER and q.get("other"):  # their own words; ticked and left empty: no answer
                    x = _line(other[0] if isinstance(other, list) and other else other, SHORT)
                elif x not in q["options"]:
                    raise ApiError("bad_input", q["id"])
                if x:
                    picked.append(x)
            v = picked if kind == "multi" else picked[0] if picked else ""
        if v:
            out[q["id"]] = v
        elif q.get("required"):
            raise ApiError("bad_input", "required")
    if not out:
        raise ApiError("bad_input", "empty")
    return out


def submit(con, slug: str, body: object) -> None:
    """Public forms only. Check the form and insert under one lock, including closure and research status."""
    with tx(con):
        f = one(con, "SELECT id, spec, closed_at FROM forms WHERE slug = ?", slug)
        if not f:
            raise ApiError("not_found")
        if one(con, "SELECT 1 FROM research_forms WHERE form_id = ?", f["id"]):
            raise ApiError("forbidden", "research_app")
        if f["closed_at"] is not None:
            raise ApiError("closed")
        if not isinstance(body, dict):
            raise ApiError("bad_input")
        if body.get("website"):  # the public page's honeypot
            return
        out = answers(json.loads(f["spec"]), body)
        if one(con, "SELECT COUNT(*) FROM form_answers WHERE form_id = ? AND created_at > ?", f["id"], core.now() - 86400)[0] >= A_DAY:
            raise ApiError("rate_limited", "form_day")
        con.execute("INSERT INTO form_answers (form_id, answers, created_at) VALUES (?, ?, ?)", (f["id"], json.dumps(out, ensure_ascii=False), core.now()))


def listing(con) -> list[tuple[str, bool, int]]:
    return [(r["slug"], r["closed_at"] is None, r["n"]) for r in rows(con, """SELECT f.slug, f.closed_at,
        (SELECT COUNT(*) FROM form_answers a WHERE a.form_id = f.id)
        + (SELECT COUNT(*) FROM research_answers a WHERE a.form_id = f.id) n FROM forms f ORDER BY f.id""")]


def forget(con) -> None:
    con.execute("DELETE FROM form_answers WHERE form_id IN (SELECT id FROM forms WHERE closed_at <= ?)", (core.now() - KEEP,))


def export(con, slug: str) -> str:
    """Owner's CSV: the time (UTC), then a column per question under its label; a multi's picks joined by "; ".
    Research adds account/name columns; anonymous rows have neither."""
    f = one(con, "SELECT id, spec, closed_at FROM forms WHERE slug = ?", slug)
    if not f:
        raise ApiError("not_found")
    qs = _questions(json.loads(f["spec"]))
    research = one(con, "SELECT 1 FROM research_forms WHERE form_id = ?", f["id"]) is not None
    safe = lambda s: "'" + s if s.lstrip()[:1] in ("=", "+", "-", "@") else s  # noqa: E731
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["at"] + (["user_id", "name"] if research else []) + [safe(q["label"]) for q in qs])
    if f["closed_at"] is not None and f["closed_at"] <= core.now() - KEEP:
        return buf.getvalue()
    # Keep legacy public answers anonymous, including the live library's earlier answers.
    records = [dict(r) | {"user_id": None, "name": "", "day_only": False} for r in rows(con,
        "SELECT answers, created_at FROM form_answers WHERE form_id = ? ORDER BY id", f["id"])]
    if research:
        records += [dict(r) | {"day_only": True} for r in rows(con, """SELECT a.answers, a.day created_at, a.user_id,
            trim(COALESCE(s.first_name, u.tg_first_name, '') || ' ' || COALESCE(s.last_name, u.tg_last_name, '')) name
            FROM research_answers a LEFT JOIN users u ON u.id = a.user_id LEFT JOIN students s ON s.user_id = a.user_id
            WHERE a.form_id = ? ORDER BY a.id""", f["id"])]
    for r in records:
        a = json.loads(r["answers"])
        stamp = "" if r["created_at"] is None else time.strftime(
            "%Y-%m-%d" if r["day_only"] else "%Y-%m-%d %H:%M", time.gmtime(r["created_at"]))
        w.writerow([stamp] + ([str(r["user_id"] or ""), safe(_line(r["name"], 300))] if research else [])
                   + [safe("; ".join(v) if isinstance(v := a.get(q["id"], ""), list) else v) for q in qs])
    return buf.getvalue()


# ------------------------------------------------------------ the page

def _question(q: dict, t: dict) -> str:
    e, qid, kind = html.escape, q["id"], q["type"]
    if kind == "text":
        field = f'<input class="in" name="{qid}" maxlength="{SHORT}" autocomplete="off" aria-label="{e(q["label"])}">'
    elif kind == "long":
        field = f'<textarea class="in" name="{qid}" maxlength="{LONG}" rows="3" aria-label="{e(q["label"])}"></textarea>'
    elif kind == "scale":
        ends = f'<div class="ends"><span>{e(q.get("low", ""))}</span><span>{e(q.get("high", ""))}</span></div>' if q.get("low") or q.get("high") else ""
        field = '<div class="chips scale">' + "".join(f'<label><input type="radio" name="{qid}" value="{n}"><span>{n}</span></label>' for n in SCALE) + f"</div>{ends}"
    else:
        box = "radio" if kind == "choice" else "checkbox"
        field = '<div class="chips">' + "".join(f'<label><input type="{box}" name="{qid}" value="{e(o)}"><span>{e(o)}</span></label>' for o in q["options"])
        if q.get("other"):
            field += f'<label><input type="{box}" name="{qid}" value="{OTHER}" class="o"><span>{e(t["other"])}</span></label>'
        field += "</div>"
        if q.get("other"):
            field += f'<input class="in other" name="{qid}~" maxlength="{SHORT}" autocomplete="off" placeholder="{e(t["otherHint"])}" aria-label="{e(t["other"])}" hidden>'
    hint = f'<small>{e(q.get("hint") or t["many"])}</small>' if q.get("hint") or kind == "multi" else ""
    req = ' data-req' if q.get("required") else ""
    star = '<i aria-hidden="true">*</i>' if req else ""
    return f'<fieldset{req}><legend>{e(q["label"])}{star}{hint}</legend>{field}<p class="e">{e(t["required"])}</p></fieldset>'


def page(con, slug: str, app_url: str = "/?startapp=research") -> tuple[int, str]:
    """(status, html) of /f/<slug>: the form, or a calm page saying there is none (404) or it is closed (410)."""
    e = html.escape
    f = one(con, "SELECT id, spec, closed_at FROM forms WHERE slug = ?", slug)
    spec = json.loads(f["spec"]) if f else {"lang": "ru"}
    t = texts.FORM_PAGE[spec["lang"]]
    if not f or f["closed_at"] is not None:
        title, line = t["closed" if f else "none"]
        body = f'<section class="note"><h1>{e(title)}</h1><p class="intro">{e(line)}</p></section>'
        return (410 if f else 404), _fill(spec["lang"], e(title), body, e(t["made"]))
    if one(con, "SELECT 1 FROM research_forms WHERE form_id = ?", f["id"]):
        body = (f'<section class="note"><h1>{e(spec["title"])}</h1><p class="intro">{e(t["research"])}</p>'
                f'<a href="{e(app_url, quote=True)}">{e(t["openApp"])}</a></section>')
        return 200, _fill(spec["lang"], e(spec["title"]), body, e(t["made"]))
    n = len(spec["sections"])
    cards = "".join(f'<section class="card"><p class="step">{i} / {n}</p>' + (f'<h2>{e(s["title"])}</h2>' if s["title"] else "")
                    + "".join(_question(q, t) for q in s["questions"]) + "</section>" for i, s in enumerate(spec["sections"], 1))
    errs = " ".join(f'data-{k}="{e(t[k])}"' for k in ("fail", "full", "shut", "empty"))
    body = f"""<div class="bar"><i id="bar"></i></div>
<form id="f" novalidate {errs}>
<header><p class="anon">{_LOCK}{e(t["anon"])}</p><h1>{e(spec["title"])}</h1><p class="intro">{e(spec["intro"])}</p></header>
{cards}
<div class="hp" aria-hidden="true"><input name="website" tabindex="-1" autocomplete="off"></div>
<button id="go">{e(t["send"])}</button><p id="msg" role="alert"></p>
</form>
<section id="done" class="note" hidden>{_CHECK}<h1>{e(t["thanks"])}</h1><p class="intro">{e(spec["thanks"])}</p></section>
<script>{_JS}</script>"""
    return 200, _fill(spec["lang"], e(spec["title"]), body, e(t["made"]))


def _fill(lang: str, title: str, body: str, foot: str) -> str:
    """The page with its slots filled in one pass, so a spec's "__BODY__" stays words."""
    got = {"LANG": lang, "TITLE": title, "BODY": body, "FOOT": foot}
    return re.sub(r"__(LANG|TITLE|BODY|FOOT)__", lambda m: got[m[1]], _HTML)


_LOCK = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H4a1.5 1.5 0 0 0-1.5 1.5v5A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5v-5A1.5 1.5 0 0 0 12 6h-.5V4.5A3.5 3.5 0 0 0 8 1Zm2 5H6V4.5a2 2 0 1 1 4 0Z"/></svg>'
_CHECK = '<svg class="ok" viewBox="0 0 72 72" width="72" height="72" aria-hidden="true"><circle cx="36" cy="36" r="36"/><path d="M22 37.5 31.5 47 50 27"/></svg>'

# the values are web/src/ui/tokens.css's (light and dark): --bg, --surface, --fill, --text*, --accent*, --danger-text,
# --card-rim, --separator, --r-group 24, --r-s 12, --ctl-l 50, --tap 44, --ease-spring
_HTML = """<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex"><title>__TITLE__</title><style>"""
_CSS = """:root{color-scheme:light dark;--bg:#F2F2F7;--card:#FFF;--fill:rgba(11,20,51,.075);--text:#0A0A0C;--t2:rgba(60,60,67,.86);--t3:rgba(60,60,67,.72);
--accent:#3B6BFF;--at:#2A57E6;--soft:rgba(59,107,255,.12);--bad:#BA342E;--sep:rgba(60,60,67,.16);
--rim:inset 0 0 0 .5px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.03),0 10px 24px -14px rgba(0,0,0,.12);--ease:cubic-bezier(.32,.72,0,1)}
@media(prefers-color-scheme:dark){:root{--bg:#000;--card:#131314;--fill:rgba(235,235,245,.12);--text:#FFF;--t2:rgba(235,235,245,.74);
--t3:rgba(235,235,245,.54);--at:#8FA8FF;--soft:rgba(59,107,255,.18);--bad:#FF8A80;--sep:rgba(255,255,255,.1);--rim:inset 0 0 0 1px rgba(255,255,255,.075)}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,system-ui,'Segoe UI',Roboto,sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:560px;margin:0 auto;padding:calc(28px + env(safe-area-inset-top)) 16px calc(36px + env(safe-area-inset-bottom))}
.bar{position:fixed;inset:0 0 auto;height:3px;z-index:1}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#3B6BFF,#7C4DFF);transform:scaleX(0);transform-origin:0 50%;transition:transform .38s var(--ease)}
header{padding:0 4px}
.anon{display:inline-flex;align-items:center;gap:6px;margin:0;padding:6px 11px;border-radius:999px;background:var(--soft);color:var(--at);font-size:12px;font-weight:600}
h1{margin:14px 0 10px;font-size:28px;line-height:1.15;font-weight:700;letter-spacing:-.02em;text-wrap:balance}
.intro{margin:0;color:var(--t2);white-space:pre-line}
.card{margin-top:16px;padding:20px;border-radius:24px;background:var(--card);box-shadow:var(--rim)}
.step{margin:0 0 4px;color:var(--at);font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
h2{margin:0;font-size:20px;line-height:1.2;font-weight:700;letter-spacing:-.01em}
fieldset{min-width:0;margin:20px 0 0;padding:0;border:0}
fieldset+fieldset{padding-top:20px;border-top:.5px solid var(--sep)}
legend{float:left;width:100%;margin-bottom:12px;padding:0;font-size:17px;line-height:1.3;font-weight:600}
legend i{margin-left:3px;color:var(--accent);font-style:normal}
legend small{display:block;padding-top:4px;color:var(--t3);font-size:13px;line-height:1.35;font-weight:400}
.chips{clear:both;display:flex;flex-wrap:wrap;gap:8px}
.chips label{position:relative;display:flex;max-width:100%;cursor:pointer}
.chips input{position:absolute;inset:0;margin:0;opacity:0;pointer-events:none}
.chips span{display:flex;align-items:center;min-height:44px;padding:10px 16px;border-radius:22px;background:var(--fill);font-weight:500;line-height:1.25;
transition:background .22s var(--ease),color .22s var(--ease),transform .12s}
.chips label:active span{transform:scale(.96)}
.chips input:checked+span{background:var(--accent);color:#FFF}
.chips input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}
.scale{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.scale span{justify-content:center;width:100%;min-height:48px;padding:0;border-radius:14px;font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}
.ends{display:flex;justify-content:space-between;gap:12px;padding-top:6px;color:var(--t3);font-size:12px}
.in{clear:both;display:block;width:100%;min-height:50px;margin:0;padding:13px 14px;border:0;border-radius:12px;background:var(--fill);color:var(--text);
font:inherit;font-size:16px;outline:0;transition:box-shadow .12s;-webkit-appearance:none;appearance:none}
.in:focus{box-shadow:0 0 0 2px var(--accent)}
.in::placeholder{color:var(--t3)}
.in[hidden]{display:none}
.other{margin-top:8px}
textarea.in{min-height:98px;resize:none;field-sizing:content}
.e{display:none;clear:both;margin:0;padding-top:8px;color:var(--bad);font-size:13px;font-weight:500}
.err .e{display:block}
.hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
button{display:block;width:100%;height:52px;margin-top:20px;border:0;border-radius:999px;background:var(--accent);color:#FFF;font:inherit;font-size:17px;font-weight:600;
cursor:pointer;transition:transform .12s,opacity .22s}
button:active{transform:scale(.98)}
button:disabled{opacity:.55}
button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
#msg{min-height:20px;margin:10px 0 0;color:var(--bad);font-size:13px;font-weight:500;text-align:center}
.foot{margin:14px 0 0;color:var(--t3);font-size:12px;text-align:center}
.note{padding:22vh 12px 0;text-align:center;animation:up .5s var(--ease) both}
.note[hidden]{display:none}
.ok{margin-bottom:8px}
.ok circle{fill:var(--soft)}
.ok path{fill:none;stroke:var(--accent);stroke-width:5;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:42;stroke-dashoffset:42;animation:draw .45s .25s var(--ease) forwards}
@keyframes up{from{opacity:0;transform:translateY(12px)}}
@keyframes draw{to{stroke-dashoffset:0}}
@media(prefers-reduced-motion:reduce){*{animation-duration:0s!important;animation-delay:0s!important;transition:none!important}}"""
_HTML += _CSS + """</style></head><body><main>__BODY__<p class="foot">__FOOT__</p></main></body></html>"""

# the draft lives in this browser's localStorage until sent; a radio taps off again (an optional question can be unanswered)
_JS = """(()=>{const f=document.getElementById('f'),go=document.getElementById('go'),msg=document.getElementById('msg'),bar=document.getElementById('bar'),
K='form:'+location.pathname,qs=[...f.querySelectorAll('fieldset')],box=x=>x.type==='radio'||x.type==='checkbox';
const has=q=>[...q.querySelectorAll('input,textarea')].some(x=>box(x)?x.checked&&(!x.classList.contains('o')||q.querySelector('.other').value.trim()):!x.classList.contains('other')&&x.value.trim());
const data=()=>{const d={};for(const x of f.elements){if(!x.name||box(x)&&!x.checked||!x.value)continue;(d[x.name]=d[x.name]||[]).push(x.value)}return d};
const sync=(save)=>{let n=0;for(const q of qs){const o=q.querySelector('.other');if(o)o.hidden=!q.querySelector('.o:checked');if(has(q)){n++;q.classList.remove('err')}}
bar.style.transform='scaleX('+n/qs.length+')';if(save)try{localStorage.setItem(K,JSON.stringify(data()))}catch{}};
const grow=x=>{if(!CSS.supports('field-sizing','content')){x.style.height='auto';x.style.height=x.scrollHeight+'px'}};
try{const d=JSON.parse(localStorage.getItem(K))||{};for(const x of f.elements){const v=d[x.name];if(!v)continue;if(box(x))x.w=x.checked=v.includes(x.value);else x.value=v[0]}}catch{}
f.querySelectorAll('textarea').forEach(grow);sync();
f.addEventListener('input',e=>{if(e.target.tagName==='TEXTAREA')grow(e.target);sync(1)});
f.addEventListener('click',e=>{const r=e.target;if(r.type!=='radio')return;const was=r.w;f.querySelectorAll('[name="'+r.name+'"]').forEach(x=>x.w=0);
if(was){r.checked=false;sync(1)}else r.w=1});
f.addEventListener('change',e=>{if(e.target.classList.contains('o')&&e.target.checked)e.target.closest('fieldset').querySelector('.other').focus()});
f.addEventListener('submit',async e=>{e.preventDefault();let bad;for(const q of qs){const m=q.hasAttribute('data-req')&&!has(q);q.classList.toggle('err',m);bad=bad||m&&q}
if(bad)return bad.scrollIntoView({behavior:'smooth',block:'center'});
if(!qs.some(has))return msg.textContent=f.dataset.empty;
go.disabled=true;msg.textContent='';
try{const r=await fetch('/api'+location.pathname,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data())});
if(!r.ok)throw r.status;
try{localStorage.removeItem(K)}catch{}
f.hidden=true;document.querySelector('.bar').hidden=true;document.getElementById('done').hidden=false;scrollTo(0,0)}
catch(c){go.disabled=false;msg.textContent=c===429?f.dataset.full:c===409||c===404?f.dataset.shut:f.dataset.fail}})})()"""


# only this page's own style and script run (by their hashes): an injected tag wouldn't, even past an escaping slip
CSP = (f"default-src 'none'; style-src {_sha(_CSS)}; script-src {_sha(_JS)}; connect-src 'self'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")
