import '@fontsource-variable/inter/opsz.css';
import './ui/tokens.css';
import './ui/base.css';
import { mount } from 'svelte';
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

// the app's language before the first render (Russian is in the bundle: at once); without the network, Russian words
void loadLang(i18n.lang).catch(() => {}).then(() => {
  // /screen: the organizer's check-in screen on a laptop (server checkin.py), the app otherwise
  mount(location.pathname === '/screen' ? Screen : App, { target: document.getElementById('app')! });
  window.__kbStarted = true;
  // the other languages when idle, so a switch in Settings is as instant as before
  setTimeout(() => { for (const l of LANGS) void loadLang(l).catch(() => {}); }, 3000);
});
