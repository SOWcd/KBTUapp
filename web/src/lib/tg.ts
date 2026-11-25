// Telegram Mini App bridge. Every call is wrapped: outside Telegram, or in an older client,
// WebApp methods exist but THROW (WebAppMethodUnsupported), and one uncaught throw at start
// leaves a blank screen. Nothing in the app calls window.Telegram directly.

import { inApp, native, scan as nativeScan, scanClose } from './native';

type Inset = { top: number; bottom: number; left: number; right: number };
export type InvoiceStatus = 'paid' | 'cancelled' | 'failed' | 'pending';
type TgUser = { id: number; first_name: string; last_name?: string; username?: string; language_code?: string; photo_url?: string };

interface WebApp {
  initData: string;
  initDataUnsafe: { user?: TgUser; start_param?: string };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  isFullscreen?: boolean;
  safeAreaInset?: Inset;
  contentSafeAreaInset?: Inset;
  isVersionAtLeast(v: string): boolean;
  ready(): void;
  expand(): void;
  close(): void;
  requestFullscreen?(): void;
  disableVerticalSwipes?(): void;
  lockOrientation?(): void;
  setHeaderColor?(c: string): void;
  setBackgroundColor?(c: string): void;
  setBottomBarColor?(c: string): void;
  onEvent(e: string, cb: (...a: unknown[]) => void): void;
  offEvent(e: string, cb: (...a: unknown[]) => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback: {
    impactOccurred(s: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(s: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  showScanQrPopup?(p: { text?: string }, cb: (text: string) => boolean | void): void;
  closeScanQrPopup?(): void;
  openLink(url: string): void;
  openTelegramLink(url: string): void;
  shareMessage?(id: string, cb?: (ok: boolean) => void): void;
  openInvoice?(url: string, cb?: (status: InvoiceStatus) => void): void;
  downloadFile?(p: { url: string; file_name: string }, cb?: (ok: boolean) => void): void;
  requestWriteAccess?(cb?: (ok: boolean) => void): void;
  readTextFromClipboard?(cb: (text: string | null) => void): void;
  addToHomeScreen?(): void;
  checkHomeScreenStatus?(cb: (s: string) => void): void;
  showAlert?(text: string): void;
  DeviceOrientation?: { start(p: { refresh_rate?: number }): void; stop(): void; beta: number | null; gamma: number | null };
}

declare global {
  interface Window { Telegram?: { WebApp?: WebApp }; __kbStarted?: boolean }
}

const W: WebApp | undefined = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;

/** Inside a real Telegram client (the script also loads in a plain browser, with platform 'unknown'). */
export const inTelegram = !!W?.initData;
/** A computer (Telegram Desktop, macOS, the web clients): the app is made for phones and works there in a phone-sized
 *  window. Telegram's phone platforms are ios, android and android_x. */
export const onComputer = inTelegram ? !/^(ios|android)/.test(W!.platform)
  : typeof matchMedia === 'function' && matchMedia('(hover: hover) and (pointer: fine)').matches; // a plain browser: a mouse, not a finger
/** An Android phone (Telegram's android / android_x, or a plain browser saying so): its own steps come first. */
export const onAndroid = inTelegram ? /^android/.test(W!.platform) : typeof navigator !== 'undefined' && /Android/.test(navigator.userAgent);

/** An iPhone or iPad (Telegram's ios, or a plain browser saying so). */
export const onIos = inTelegram ? W!.platform === 'ios' : typeof navigator !== 'undefined' && /iPhone|iPad|iPod/.test(navigator.userAgent);

function can(v: string): boolean {
  try { return inTelegram && W!.isVersionAtLeast(v); } catch { return false; }
}

export function tgTry(fn: (w: WebApp) => void): void {
  if (!inTelegram || !W) return;
  try { fn(W); } catch { /* unsupported here; the app goes on without it */ }
}

export const tg = {
  initData: W?.initData ?? '',
  user: inTelegram ? W?.initDataUnsafe?.user ?? null : null,
  // a link Telegram opened as a plain URL (the guard bot's join request app: web_app_url) carries it in the query; so
  // does the iPhone app's launch from a notification (ios/: the push's "start")
  startParam: inTelegram || inApp ? W?.initDataUnsafe?.start_param || new URLSearchParams(location.search).get('startapp') || '' : '',
  platform: W?.platform ?? 'unknown',
  /** the coarse device kind the server keeps (a Telegram computer client is desktop; its web clients and a plain browser, web) */
  kind: onAndroid ? 'android' : onIos ? 'ios' : inTelegram && !/^web/.test(W!.platform) ? 'desktop' : 'web',
  // outside Telegram its script says 'light' whatever the phone uses: the system's own scheme there
  colorScheme: (): 'light' | 'dark' => (inTelegram ? W?.colorScheme : null) ?? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'),
  can,
  /** a computer's Mini App window to full screen (Bot API 8.0+); false where the client can't */
  canFullscreen: (): boolean => onComputer && can('8.0') && !W?.isFullscreen,
  fullscreen: (): void => tgTry((w) => w.requestFullscreen?.()),
};

let felt = 0; // when the last haptic fired: the app-wide tap below stays quiet when a handler already gave one
const buzz = (fn: (h: NonNullable<WebApp['HapticFeedback']>) => void) => { felt = performance.now(); tgTry((w) => fn(w.HapticFeedback)); };
export const haptic = {
  tap: () => buzz((h) => h.impactOccurred('light')),
  soft: () => buzz((h) => h.impactOccurred('soft')),
  rigid: () => buzz((h) => h.impactOccurred('rigid')),
  select: () => buzz((h) => h.selectionChanged()),
  ok: () => buzz((h) => h.notificationOccurred('success')),
  warn: () => buzz((h) => h.notificationOccurred('warning')),
  error: () => buzz((h) => h.notificationOccurred('error')),
};

/** Every tap on something tappable is felt, one listener instead of a
 *  haptic in every handler; a handler's own haptic (ok, error, select...) wins, data-nohaptic opts a part out. */
export function hapticTaps(): void {
  if (!inTelegram) return;
  document.addEventListener('click', (e) => {
    const el = (e.target as Element | null)?.closest?.('button, a[href], [role="button"], [role="tab"], [role="switch"], [role="radio"], label, summary');
    if (!el || el.closest('[data-nohaptic]') || (el as HTMLButtonElement).disabled || el.getAttribute('aria-disabled') === 'true' || performance.now() - felt < 120) return;
    haptic.tap();
  });
}

/** Start-up: full screen, no swipe-to-close while scrolling, colours that match the theme. */
export function boot(bg: string): void {
  if (!inTelegram) return;
  tgTry((w) => w.ready());
  tgTry((w) => w.expand());
  if (can('7.7')) tgTry((w) => w.disableVerticalSwipes?.());
  // full screen on a phone only: on a computer it filled the whole monitor with the phone layout (a student's screenshot)
  if (can('8.0') && !onComputer) tgTry((w) => w.requestFullscreen?.());
  // portrait only: the phone turned sideways keeps the app upright; Telegram on phones, 8.0+
  if (can('8.0') && !onComputer) tgTry((w) => w.lockOrientation?.());
  paint(bg);
}

/** Telegram's own surfaces (under the webview, the bottom bar) follow the app background, so nothing flashes white. */
export function paint(bg: string): void {
  // (one per system theme, index.html) iOS's home-screen status bar ignores a changed content: it repaints only for a new
  // meta, so each is swapped for a fresh copy (a theme switch left the strip black over the light page; owner, Nov 24)
  if (!inTelegram) {
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
      if (m.getAttribute('content') === bg) return;
      const n = m.cloneNode() as HTMLMetaElement;
      n.content = bg;
      m.replaceWith(n);
    });
    return;
  }
  if (can('6.1')) { tgTry((w) => w.setBackgroundColor?.(bg)); tgTry((w) => w.setHeaderColor?.(bg)); }
  if (can('7.10')) tgTry((w) => w.setBottomBarColor?.(bg));
}

export function on(event: string, cb: () => void): () => void {
  if (!inTelegram && event === 'themeChanged') {
    const scheme = matchMedia('(prefers-color-scheme: light)');
    scheme.addEventListener('change', cb);
    return () => scheme.removeEventListener('change', cb);
  }
  tgTry((w) => w.onEvent(event, cb));
  return () => tgTry((w) => w.offEvent(event, cb));
}

/** The app's icon on the phone's home screen (Bot API 8.0): Telegram's own dialog, one tap (wanted an
 *  arrow to the ••• menu; the API does it without one). Status: 'unsupported' | 'unknown' | 'added' | 'missed'. */
export const homeScreen = {
  status: (): Promise<string> => new Promise((r) => {
    if (!can('8.0')) return r('unsupported');
    tgTry((w) => w.checkHomeScreenStatus?.(r));
    setTimeout(() => r('unknown'), 1500); // a client that never answers
  }),
  add: () => can('8.0') && tgTry((w) => w.addToHomeScreen?.()),
  /** Telegram's own alert: a hint too long for a toast */
  help: (text: string) => tgTry((w) => w.showAlert?.(text)),
  android: () => onAndroid, // Telegram X (android_x) too: its launchers swallow the dialog the same way
};

let webBack: (() => void) | undefined;
export const backButton = {
  show: () => can('6.1') && tgTry((w) => w.BackButton.show()),
  hide: () => can('6.1') && tgTry((w) => w.BackButton.hide()),
  onClick(cb: () => void) {
    if (!inTelegram) {
      webBack = cb;
      return () => { if (webBack === cb) webBack = undefined; };
    }
    tgTry((w) => w.BackButton.onClick(cb));
    return () => tgTry((w) => w.BackButton.offClick(cb));
  },
  click: () => webBack?.(),
};

export const telegramAppLink = (p = ''): string => `https://t.me/KBTUappBot?startapp${p ? '=' + encodeURIComponent(p) : ''}`;

export function openTelegramLink(url: string): void {
  if (inTelegram) tgTry((w) => w.openTelegramLink(url));
  else location.assign(url);
}

/** `web`: always the browser, never a Telegram deep link (an online event's meeting) */
export function openLink(url: string, web = false): void {
  if (!web && url.startsWith('https://t.me/')) openTelegramLink(url);
  else if (inTelegram) tgTry((w) => w.openLink(url));
  else window.open(url, '_blank', 'noopener');
}

/** QR scanner (phones only): the iPhone app's own, else Telegram's popup. `onText` returns true to close it.
 *  Returns false when unavailable. */
export function scanQr(text: string, onText: (value: string) => boolean): boolean {
  if (native.has('scan')) { nativeScan(text, onText); return true; }
  if (!can('6.4') || !W?.showScanQrPopup) return false;
  tgTry((w) => w.showScanQrPopup!({ text }, (v) => onText(v)));
  return true;
}

export function closeScanner(): void { scanClose(); if (can('6.4')) tgTry((w) => w.closeScanQrPopup?.()); }

/** Telegram's own payment window can take Stars here: they came with Bot API 7.4, an older client hides the option. */
export const canStars = (): boolean => can('7.4') && !!W?.openInvoice;

export function openInvoice(url: string, cb: (status: InvoiceStatus) => void): void {
  try { W!.openInvoice!(url, cb); } catch { cb('failed'); } // another invoice is open, or the link is refused
}

/** true: sent; false: the picker closed; null: this client can't share a card (Telegram Desktop said UNSUPPORTED). */
export function shareMessage(preparedId: string): Promise<boolean | null> {
  return new Promise((done) => {
    if (!can('8.0') || !W?.shareMessage) return done(null);
    const off = on('shareMessageFailed', () => { off(); done(null); });
    tgTry((w) => w.shareMessage!(preparedId, (ok) => { off(); done(!!ok); }));
  });
}

/** Everything shared into chats is our bot's card — text and a button, never a bare link: the server
 *  prepares it from its own templates (savePreparedInlineMessage, initData-checked), then Telegram shows the chat
 *  picker. A failure throws (the caller says so) instead of falling back to a link; a plain t.me share link only
 *  where there are no cards at all (Telegram older than Bot API 8.0, a plain browser). */
/** ready: the card is made and the picker opens now (the caller's "making the link" ends there, not when a chat is picked) */
/** the capsule's "Making the link…" for every share (ui.svelte.ts sets it: tg.ts can't import the state) */
let shareBusy: (on: boolean) => void = () => {};
export function onShareBusy(f: (on: boolean) => void): void { shareBusy = f; }

export async function shareCard(card: Record<string, string | number | boolean | null>, link: string, text: string, ready?: () => void): Promise<boolean> {
  shareBusy(true);
  try { return await shareVia(card, link, text, () => { shareBusy(false); ready?.(); }); }
  finally { shareBusy(false); }
}

/** Telegram's share picker with our words first, the link under them (its `text` param would go below the link). */
export function tgShare(link: string, text: string) {
  openLink(`https://t.me/share/url?url=${encodeURIComponent(`${text}\n${link}`)}`);
}

async function shareVia(card: Record<string, string | number | boolean | null>, link: string, text: string, ready: () => void): Promise<boolean> {
  if (inTelegram && can('8.0') && W?.shareMessage) {
    // the server reads initData from the header like every API call; the dev server still reads it from the body
    const r = await fetch('/api/share', { method: 'POST', headers: { Authorization: `tma ${W.initData}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...card, initData: W.initData }) });
    const { id } = await r.json();
    if (!id) throw new Error('share');
    ready();
    const sent = await shareMessage(id); // true once the user picked a chat
    if (sent !== null) return sent;
    // a client without cards (a user on Telegram Desktop): Telegram's own picker with the link instead
  }
  if (!inTelegram) {
    // the web app: the server makes the same link its card's button would carry (an award or club link is minted there)
    const r = await fetch('/api/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...card, link: true }) });
    const made = r.ok ? (await r.json()).link : null;
    if (typeof made === 'string') link = made;
  }
  ready();
  tgShare(link, text);
  return false; // the link opens Telegram's own picker: we never learn whether it was sent
}

/** Files (CSV) — `<a download>` does nothing in Telegram webviews; Bot API 8.0 has a real download. */
export function downloadFile(url: string, fileName: string): void {
  if (can('8.0') && W?.downloadFile) { tgTry((w) => w.downloadFile!({ url, file_name: fileName })); return; }
  const a = document.createElement('a');
  a.href = url; a.download = fileName; a.click();
}

export function requestWriteAccess(): Promise<boolean> {
  return new Promise((done) => {
    if (!can('6.9') || !W?.requestWriteAccess) return done(false);
    tgTry((w) => w.requestWriteAccess!((ok) => done(!!ok)));
  });
}

/** The clipboard's text: Telegram's own reader where it answers (6.4+; only some launches may read it), else the
 *  browser's; null when neither may (the field stays to paste by hand). Telegram can stay silent: a second's wait */
export async function readClipboard(): Promise<string | null> {
  if (can('6.4') && W?.readTextFromClipboard) {
    const got = await new Promise<string | null>((done) => {
      const t = setTimeout(() => done(null), 1000);
      tgTry((w) => w.readTextFromClipboard!((x) => { clearTimeout(t); done(x || null); }));
    });
    if (got) return got;
  }
  try { return (await navigator.clipboard?.readText()) || null; } catch { return null; }
}

export function deviceOrientation() { return can('8.0') ? W?.DeviceOrientation ?? null : null; }
