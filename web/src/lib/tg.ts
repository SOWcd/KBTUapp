// Telegram Mini App bridge. Every call is wrapped: outside Telegram, or in an older client,
// WebApp methods exist but THROW (WebAppMethodUnsupported), and one uncaught throw at start
// leaves a blank screen. Nothing in the app calls window.Telegram directly.

type Inset = { top: number; bottom: number; left: number; right: number };
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
  downloadFile?(p: { url: string; file_name: string }, cb?: (ok: boolean) => void): void;
  requestWriteAccess?(cb?: (ok: boolean) => void): void;
  addToHomeScreen?(): void;
  checkHomeScreenStatus?(cb: (s: string) => void): void;
  DeviceOrientation?: { start(p: { refresh_rate?: number }): void; stop(): void; beta: number | null; gamma: number | null };
}

declare global {
  interface Window { Telegram?: { WebApp?: WebApp }; __kbStarted?: boolean }
}

const W: WebApp | undefined = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;

/** Inside a real Telegram client (the script also loads in a plain browser, with platform 'unknown'). */
export const inTelegram = !!W && W.platform !== 'unknown' && !!W.initData;
/** A computer (Telegram Desktop, macOS, the web clients): the app is made for phones and works there in a phone-sized
 *  window. Telegram's phone platforms are ios, android and android_x. */
export const onComputer = inTelegram ? !/^(ios|android)/.test(W!.platform)
  : typeof matchMedia === 'function' && matchMedia('(hover: hover) and (pointer: fine)').matches; // a plain browser: a mouse, not a finger (Oct 13)

function can(v: string): boolean {
  try { return inTelegram && W!.isVersionAtLeast(v); } catch { return false; }
}

export function tgTry(fn: (w: WebApp) => void): void {
  if (!W) return;
  try { fn(W); } catch { /* unsupported here; the app goes on without it */ }
}

export const tg = {
  initData: W?.initData ?? '',
  user: W?.initDataUnsafe?.user ?? null,
  startParam: W?.initDataUnsafe?.start_param ?? '',
  platform: W?.platform ?? 'unknown',
  colorScheme: (): 'light' | 'dark' => W?.colorScheme ?? 'dark',
  can,
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

/** Every tap on something tappable is felt (owner, Oct 18: "the app should feel alive"), one listener instead of a
 *  haptic in every handler; a handler's own haptic (ok, error, select...) wins, data-nohaptic opts a part out. */
export function hapticTaps(): void {
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
  // full screen on a phone only: on a computer it filled the whole monitor with the phone layout (a student's screenshot, Oct 11)
  if (can('8.0') && !onComputer) tgTry((w) => w.requestFullscreen?.());
  // portrait only (owner, Oct 14): the phone turned sideways keeps the app upright; Telegram on phones, 8.0+
  if (can('8.0') && !onComputer) tgTry((w) => w.lockOrientation?.());
  paint(bg);
}

/** Telegram's own surfaces (under the webview, the bottom bar) follow the app background, so nothing flashes white. */
export function paint(bg: string): void {
  if (!inTelegram) return;
  if (can('6.1')) { tgTry((w) => w.setBackgroundColor?.(bg)); tgTry((w) => w.setHeaderColor?.(bg)); }
  if (can('7.10')) tgTry((w) => w.setBottomBarColor?.(bg));
}

export function on(event: string, cb: () => void): () => void {
  tgTry((w) => w.onEvent(event, cb));
  return () => tgTry((w) => w.offEvent(event, cb));
}

/** The app's icon on the phone's home screen (Bot API 8.0): Telegram's own dialog, one tap (owner, Oct 26, wanted an
 *  arrow to the ••• menu; the API does it without one). Status: 'unsupported' | 'unknown' | 'added' | 'missed'. */
export const homeScreen = {
  status: (): Promise<string> => new Promise((r) => {
    if (!can('8.0')) return r('unsupported');
    tgTry((w) => w.checkHomeScreenStatus?.(r));
    setTimeout(() => r('unknown'), 1500); // a client that never answers
  }),
  add: () => can('8.0') && tgTry((w) => w.addToHomeScreen?.()),
};

export const backButton = {
  show: () => can('6.1') && tgTry((w) => w.BackButton.show()),
  hide: () => can('6.1') && tgTry((w) => w.BackButton.hide()),
  onClick: (cb: () => void) => tgTry((w) => w.BackButton.onClick(cb)),
};

export function openLink(url: string): void {
  if (inTelegram) { tgTry((w) => (url.startsWith('https://t.me/') ? w.openTelegramLink(url) : w.openLink(url))); return; }
  window.open(url, '_blank', 'noopener');
}

/** QR scanner (phones only). `onText` returns true to close the popup. Returns false when unavailable. */
export function scanQr(text: string, onText: (value: string) => boolean): boolean {
  if (!can('6.4') || !W?.showScanQrPopup) return false;
  tgTry((w) => w.showScanQrPopup!({ text }, (v) => onText(v)));
  return true;
}

export function closeScanner(): void { if (can('6.4')) tgTry((w) => w.closeScanQrPopup?.()); }

export function shareMessage(preparedId: string): Promise<boolean> {
  return new Promise((done) => {
    if (!can('8.0') || !W?.shareMessage) return done(false);
    tgTry((w) => w.shareMessage!(preparedId, (ok) => done(!!ok)));
  });
}

/** Everything shared into chats is our bot's card — text and a button, never a bare link (owner, Oct 4): the server
 *  prepares it from its own templates (savePreparedInlineMessage, initData-checked), then Telegram shows the chat
 *  picker. A failure throws (the caller says so) instead of falling back to a link; a plain t.me share link only
 *  where there are no cards at all (Telegram older than Bot API 8.0, a plain browser). */
/** ready: the card is made and the picker opens now (the caller's "making the link" ends there, not when a chat is picked) */
export async function shareCard(card: Record<string, string>, link: string, text: string, ready?: () => void): Promise<boolean> {
  if (inTelegram && can('8.0') && W?.shareMessage) {
    // the server reads initData from the header like every API call; the dev server still reads it from the body
    const r = await fetch('/api/share', { method: 'POST', headers: { Authorization: `tma ${W.initData}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...card, initData: W.initData }) });
    const { id } = await r.json();
    if (!id) throw new Error('share');
    ready?.();
    return await shareMessage(id); // true once the user picked a chat
  }
  ready?.();
  openLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`);
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

export function deviceOrientation() { return can('8.0') ? W?.DeviceOrientation ?? null : null; }
