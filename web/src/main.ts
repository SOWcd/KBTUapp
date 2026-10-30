import '@fontsource-variable/inter/opsz.css';
import './ui/tokens.css';
import './ui/base.css';
import { mount, unmount } from 'svelte';
import App from './App.svelte';
import Screen from './screens/Screen.svelte';
import { boot, hapticTaps, tg } from './lib/tg';
import { i18n, loadLang, LANGS } from './lib/i18n/index.svelte';
import { applyTheme, initialTheme } from './lib/state/theme.svelte';
import './lib/state/power.svelte'; // power saving's look before the first paint

document.documentElement.lang = i18n.lang;
// theme before the first paint: no white flash in dark mode
applyTheme(initialTheme(tg.colorScheme()));
boot(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#07080F');

// A deploy replaces the lazily loaded screens, so an app opened before it fails to load its next sheet and the tap
// does nothing: reload into the new build.
// At most once a minute, so a real outage can't loop.
window.addEventListener('vite:preloadError', (e) => {
  try {
    if (Date.now() - Number(sessionStorage.getItem('kb-reloaded') ?? 0) < 60_000) return;
    sessionStorage.setItem('kb-reloaded', String(Date.now()));
  } catch { /* no storage: reload anyway */ }
  e.preventDefault();
  location.reload();
});

// WebKit (every iPhone, Telegram's webview too) applies :active only when a touch listener sits on the element or above
// it; without one, buttons outside the swipeable tabs and sheets didn't react to a press at all.
document.addEventListener('touchstart', () => {}, { passive: true });
hapticTaps();

// Outside Telegram (a plain browser) the app can't sign in: a page says where it lives first (owner, Oct 30). Told apart
// by Telegram's launch parameters, not by telegram.org's script, which a filter or a bad network can keep from a real
// Telegram user (review P3); dev, and "continue in the browser" in this tab, go straight in.
function fromTelegram(): boolean {
  if (import.meta.env.DEV || /[#?&]tgWebApp(Data|Platform)=/.test(location.hash + location.search) || /Telegram/i.test(navigator.userAgent)) return true;
  // telegram-web-app.js keeps the launch parameters here across a reload (an empty "{}" in a plain browser too)
  try { return /tgWebApp(Data|Platform)/.test(sessionStorage.getItem('__telegram__initParams') ?? '') || sessionStorage.getItem('kb-web') === '1'; } catch { return false; }
}
// the link that opens the app in Telegram; a start parameter (a short link's) passes on only in Telegram's own grammar
function telegramLink(): string {
  const p = new URLSearchParams(location.search).get('startapp') ?? new URLSearchParams(location.hash.slice(1)).get('tgWebAppStartParam');
  return p && /^[A-Za-z0-9_-]{1,64}$/.test(p) ? `https://t.me/KBTUappBot?startapp=${p}` : 'https://t.me/KBTUappBot?startapp';
}

// the app's language before the first render (Russian is in the bundle: at once); without the network, Russian words
void loadLang(i18n.lang).catch(() => {}).then(async () => {
  const app = document.getElementById('app')!;
  // /show (owner, Oct 29; /screen, the first name, still works): the organizer's big screen on a laptop (server
  // checkin.py), the app otherwise (the screen into the body: #app is a phone-wide column on a computer)
  if (/^\/(show|screen)\/?$/.test(location.pathname)) mount(Screen, { target: document.body });
  else if (fromTelegram()) mount(App, { target: app });
  else {
    const Gate = (await import('./screens/OpenInTelegram.svelte')).default;
    const gate = mount(Gate, { target: app, props: { link: telegramLink(), oncontinue: () => {
      try { sessionStorage.setItem('kb-web', '1'); } catch { /* no storage: in for this load only */ }
      void unmount(gate); mount(App, { target: app });
    } } });
  }
  window.__kbStarted = true;
  // the other languages when idle, so a switch in Settings is as instant as before
  setTimeout(() => { for (const l of LANGS) void loadLang(l).catch(() => {}); }, 3000);
});
