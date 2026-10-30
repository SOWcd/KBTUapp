"""The page between the app and the phone's calendar (/cal/<token>), opened from Settings in the phone's browser.
Apple's calendars subscribe to webcal:// themselves: there the page hands it over at once, its button for a dismissed
prompt. webcal:// does nothing on Android: there it leads with Google Calendar and offers the feed's address to copy
for any other app. The token is in the address, so the page fetches nothing from anywhere (CSP enforces it)."""
from __future__ import annotations

import base64
import hashlib
import html
import re
from string import Template
from urllib.parse import quote

from . import texts

# web/src/ui/KbtuMark.svelte, the app's mark
MARK = ('<svg class="mk" viewBox="0 0 28 24"><g fill="currentColor"><rect x="1" y="1.5" width="26" height="4" rx="1.5"/>'
        '<rect x="2" y="7" width="3" height="11" rx="1.5"/><rect x="7.25" y="7" width="3" height="11" rx="1.5"/>'
        '<rect x="12.5" y="7" width="3" height="11" rx="1.5"/><rect x="17.75" y="7" width="3" height="11" rx="1.5"/>'
        '<rect x="23" y="7" width="3" height="11" rx="1.5"/><rect x="0" y="19.5" width="28" height="3" rx="1.5"/></g></svg>')
# lucide's arrow-up-right (the row leaves for Google), copy and check
ICON = '<svg class="ic" aria-hidden="true" viewBox="0 0 24 24" fill="none"stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{}</svg>'
OUT = ICON.format('<path d="M7 7h10v10M7 17 17 7"/>')
COPY = ICON.format('<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>')
DONE = ICON.format('<path d="M20 6 9 17l-5-5"/>')

# the app's tokens (web/src/ui/tokens.css); the phone's own font (a web font would be a request), the app's Inter if installed
CSS = """
:root{color-scheme:light dark;--bg:#F3F5FB;--card:#FFF;--line:rgba(11,20,51,.08);--text:#0B1433;--text-2:rgba(11,20,51,.7);
 --text-3:rgba(11,20,51,.5);--accent:#3B6BFF;--accent-text:#2A57E6;--kb:#E8EEFF;--mine:#F0F1F5;
 --ok:#117640;--shadow:0 1px 2px rgba(24,36,90,.05),0 18px 40px -14px rgba(24,36,90,.2);--lift:0 10px 22px -12px rgba(59,107,255,.6)}
@media (prefers-color-scheme:dark){:root{--bg:#07080F;--card:#11131E;--line:rgba(255,255,255,.07);--text:#F4F6FF;
 --text-2:rgba(240,243,255,.68);--text-3:rgba(232,236,255,.42);--accent-text:#8FA8FF;--kb:#19254B;
 --mine:#1D1F2A;--ok:#5FD99A;--shadow:inset 0 0 0 1px rgba(255,255,255,.06),0 24px 48px -18px #000;--lift:0 10px 22px -10px #000}}
*{box-sizing:border-box;margin:0}
html{background:var(--bg)}
body{min-height:100vh;min-height:100dvh;display:flex;flex-direction:column;color:var(--text);text-align:center;
 padding:max(24px,env(safe-area-inset-top)) max(20px,env(safe-area-inset-right)) max(16px,env(safe-area-inset-bottom)) max(20px,env(safe-area-inset-left));
 font:17px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,Inter,system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}
main,footer{width:100%;max-width:380px;margin:0 auto}
main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center}
h1{margin-top:40px;font-size:clamp(24px,7.4vw,30px);line-height:1.15;font-weight:700;letter-spacing:-.022em;text-wrap:balance}
p{margin-top:10px;max-width:21em;color:var(--text-2);text-wrap:balance}
footer{padding-top:28px}
/* the phone's calendar, an evening: one thing of mine, and a KBTU event arriving (opaque, as a calendar's: over the hour lines) */
.day{position:relative;width:100%;max-width:300px;padding:8px 0;border-radius:26px;background:var(--card);box-shadow:var(--shadow);text-align:left}
.day b{display:flex;align-items:center;gap:10px;height:34px;padding:0 16px;color:var(--text-3);
 font-size:11px;font-weight:500;line-height:1;font-variant-numeric:tabular-nums}
.day b::after{content:"";flex:1;height:1px;background:var(--line)}
.ev{position:absolute;left:58px;right:14px;display:flex;flex-direction:column;gap:6px;padding:8px 10px 0 13px;border-radius:8px;overflow:hidden}
.ev::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--c)}
.ev i{display:block;height:6px;border-radius:3px;background:var(--c);opacity:.38}
.mine{--c:var(--text-3);top:26px;height:25px;background:var(--mine)}
.mine i{width:42%;opacity:.45}
.kb{--c:var(--accent);top:60px;height:49px;background:var(--kb);box-shadow:var(--lift);
 animation:arrive .8s cubic-bezier(.32,.72,0,1) .35s both}
.kb span{display:flex;align-items:center;gap:6px;color:var(--accent-text)}
.kb span i{flex:0 0 52%;height:7px;background:currentColor;opacity:.55}
.kb>i{width:34%;opacity:.3}
.mk{width:14px;height:12px;flex:none}
@keyframes arrive{from{opacity:0;transform:translateY(10px) scale(.96)}}
@media (prefers-reduced-motion:reduce){.kb{animation:none}}
.go,.alt{display:flex;align-items:center;justify-content:center;gap:7px;width:100%;border:0;border-radius:999px;font:inherit;
 font-weight:600;letter-spacing:-.01em;text-decoration:none;cursor:pointer;transition:transform .3s cubic-bezier(.34,1.45,.5,1),opacity .2s}
.go{height:52px;background:var(--accent);color:#fff}
.alt{height:50px;margin-top:6px;background:none;color:var(--accent-text)}
.go:active,.alt:active{transform:scale(.97);opacity:.85;transition-duration:.08s}
.go:focus-visible,.alt:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.ic{width:17px;height:17px;flex:none}
.alt .ic+.ic,.alt.done .ic:first-child{display:none}
.alt.done{color:var(--ok)}.alt.done .ic+.ic{display:block}
@media (min-width:600px) and (min-height:720px){body{justify-content:center}main{flex:none}}
@media (max-height:520px){.day{zoom:.75}h1{margin-top:28px}}
@media (max-height:400px){.day{display:none}h1{margin-top:0}}
.off{position:fixed;top:0;left:0;opacity:0}
"""

# Apple: hand webcal:// over at once. Copy: the clipboard where it's allowed, a selected field (old WebViews) where not
JS = """
var go = document.getElementById("go"), copy = document.getElementById("copy");
if (go.hasAttribute("data-auto")) location.href = go.href;
if (copy) {
  var label = copy.querySelector("span"), idle = label.textContent, timer;
  var done = function () {
    copy.classList.add("done"); label.textContent = copy.getAttribute("data-done");
    clearTimeout(timer); timer = setTimeout(function () { copy.classList.remove("done"); label.textContent = idle; }, 2000);
  };
  var old = function (url) {
    var f = document.createElement("textarea"), ok = false;
    f.value = url; f.setAttribute("readonly", ""); f.className = "off";
    document.body.appendChild(f); f.select(); f.setSelectionRange(0, url.length);
    try { ok = document.execCommand("copy"); } catch (e) {}
    f.remove(); ok ? done() : window.prompt("", url);
  };
  copy.onclick = function () {
    var url = copy.getAttribute("data-url");
    navigator.clipboard ? navigator.clipboard.writeText(url).then(done, function () { old(url); }) : old(url);
  };
}
"""

PAGE = Template("""<!doctype html><html lang="$lang"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#F3F5FB">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#07080F">
<title>$title</title><style>$css</style></head><body>
<main><div class="day" aria-hidden="true"><b>17:00</b><b>18:00</b><b>19:00</b><b>20:00</b>
<div class="ev mine"><i></i></div><div class="ev kb"><span>$mark<i></i></span><i></i></div></div>
<h1>$title</h1><p>$text</p></main>
<footer>$buttons</footer><script>$js</script></body></html>""")


def _sha(s: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"


# nothing from anywhere, only our own style and script (by their hashes: an injected tag wouldn't run)
CSP = f"default-src 'none'; style-src {_sha(CSS)}; script-src {_sha(JS)}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


def render(domain: str, token: str, lang: str, user_agent: str) -> str:
    """The page in ru, kk or en, for an Apple device or any other; everything put into it escaped."""
    title, text, subscribe, google, copy, copied = map(html.escape, texts.CAL_PAGE[lang])
    feed = f"{domain}/cal/{token}.ics"
    to_google = html.escape("https://calendar.google.com/calendar/render?cid=" + quote(f"webcal://{feed}", safe=""))
    if re.search(r"iPhone|iPad|iPod|Macintosh", user_agent):  # an iPad's Safari says Macintosh too
        buttons = (f'<a class="go" id="go" data-auto href="{html.escape(f"webcal://{feed}")}">{subscribe}</a>'
                   f'<a class="alt" href="{to_google}">{google}{OUT}</a>')
    else:
        buttons = (f'<a class="go" id="go" href="{to_google}">{google}</a><button class="alt" id="copy" type="button" '
                   f'data-url="{html.escape(f"https://{feed}")}" data-done="{copied}">{COPY}{DONE}<span aria-live="polite">{copy}</span></button>')
    return PAGE.substitute(lang=lang, title=title, text=text, css=CSS, js=JS, mark=MARK, buttons=buttons)
