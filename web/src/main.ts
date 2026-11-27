import '@fontsource-variable/inter/opsz.css';
import './ui/tokens.css';
import './ui/base.css';
import { mount } from 'svelte';
import App from './App.svelte';
import { boot, hapticTaps, inTelegram, onAndroid, tg } from './lib/tg';
import { bootOut } from './lib/boot';
import { native } from './lib/native';
import { i18n, loadLang } from './lib/i18n/index.svelte';
import { applyTheme, initialTheme } from './lib/state/theme.svelte';
import './lib/state/power.svelte'; // power saving's look before the first paint
import './lib/state/keyboard.svelte'; // the app's box at its height without a keyboard, before the first paint

document.documentElement.lang = i18n.lang;
if (!inTelegram && !/^\/(show|screen)\/?$/.test(location.pathname)) document.documentElement.dataset.web = '';
// the iPhone app draws the tab bar itself (UITabBar): Nav keeps only its corner button (lib/native.ts 'tabs')
if (native.has('tabs')) document.documentElement.dataset.ntabs = '';
// Telegram on Android reports its bottom inset (the system bar, 48 px) though the web view already ends above that bar
// or the bar is hidden in fullscreen: tokens.css drops it there (measured Nov 27, startapp=vp: dock 58 px off the bottom)
if (inTelegram && onAndroid) document.documentElement.dataset.android = '';
// theme before the first paint: no white flash in dark mode
applyTheme(initialTheme(tg.colorScheme()));
boot(getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#000');

// A deploy replaces the lazily loaded screens, so an app opened before it fails to load its next sheet and the tap
// does nothing: reload into the new build.
// At most once in 15 s, so a real outage can't loop fast (a minute left a screen blank after two deploys in a row).
window.addEventListener('vite:preloadError', (e) => {
  try {
    if (Date.now() - Number(sessionStorage.getItem('kb-reloaded') ?? 0) < 15_000) return;
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
void loadLang(i18n.lang).catch(() => {}).then(async () => {
  const app = document.getElementById('app')!;
  // /show (owner, Oct 29; /screen, the first name, still works): the organizer's big screen on a laptop (server
  // checkin.py), the app otherwise (the screen into the body: #app is a phone-wide column on a computer)
  // (its own chunk: the app's first chunk doesn't carry it, nor the QR encoder it draws with)
  // /show?lib=<key>: a library room's seats on its wall (screens/library/LibraryScreen.svelte), its own chunk too
  if (/^\/(show|screen)\/?$/.test(location.pathname)) mount((await (new URLSearchParams(location.search).has('lib') ? import('./screens/library/LibraryScreen.svelte') : import('./screens/Screen.svelte'))).default, { target: document.body });
  // the design system's lab (every ui/ component in every state): the dev server only, its own chunk, `?lab` in the URL;
  // a production build drops this branch and the chunk with it
  else if (import.meta.env.DEV && new URLSearchParams(location.search).has('lab')) bootOut(), mount((await import('./screens/lab/Lab.svelte')).default, { target: app });
  else if (inTelegram) bootOut(), mount(App, { target: app }); // (index.html's boot screen is for outside Telegram: WebEntrance takes it over)
  else mount((await import('./screens/WebEntrance.svelte')).default, { target: app });
  window.__kbStarted = true; // (the other languages load with Settings: profile/SettingsList.svelte)
});

// The service worker (sw.ts): the app opens without the network, with my tickets. Production only, and 2 s after the page
// has loaded: never in the way of the first paint. (Telegram on iOS has no service workers: there it's the network, as before.)
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  addEventListener('load', () => setTimeout(() => void navigator.serviceWorker.register('./sw.js', { updateViaCache: 'none' }).catch(() => {}), 2000));
}
