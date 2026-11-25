// The iPhone app's bridge (ios/KBTUApp/WebController.swift). The shell puts window.kbNative = { v, caps } in before any
// script and answers messageHandlers.kb with a promise. A plain browser and Telegram have neither: has() is false and
// every caller keeps its web way. v is the bridge's version: a new capability or a changed message bumps it on both
// sides, and the web checks the capability, never the version, so an old app keeps working with a new web.
import type { EventCard } from './api';

type Cap = 'apple' | 'push' | 'scan' | 'tabs' | 'tickets' | 'tglink';
interface Shell { v: number; caps: string[]; scanned?: (text: string) => boolean; tab?: (id: string) => void }
type Kb = { postMessage(m: unknown): Promise<unknown> };

declare global {
  interface Window { kbNative?: Shell; webkit?: { messageHandlers?: { kb?: Kb } } }
}

const shell: Shell | undefined = typeof window !== 'undefined' ? window.kbNative : undefined;
const kb = (): Kb | undefined => (typeof window !== 'undefined' ? window.webkit?.messageHandlers?.kb : undefined);

/** Inside the iPhone app (any bridge version). */
export const inApp = !!shell && !!kb();

export const native = {
  v: shell?.v ?? 0,
  has: (cap: Cap): boolean => inApp && Array.isArray(shell!.caps) && shell!.caps.includes(cap),
  call: <T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> => kb()!.postMessage({ cmd, ...args }) as Promise<T>,
};

/** The policy's "iPhone app and Sign in with Apple" clause (server logic/apple.py CONSENT): given at the Apple button
 *  and at Apple's notifications prompt */
export const APPLE_CONSENT = 'ios1';

/** A random nonce for one Sign in with Apple tap: the shell hashes it into Apple's request, the server checks it */
export const nonce = (): string => Array.from(crypto.getRandomValues(new Uint8Array(32)), (b) => b.toString(16).padStart(2, '0')).join('');

/** Apple's identity token for this tap, or null when the person closed Apple's sheet */
export async function appleToken(n: string): Promise<string | null> {
  try { return (await native.call<{ token: string } | null>('apple', { nonce: n }))?.token ?? null; }
  catch { return null; }
}

/** The scanner on top: each code read goes to onText, which says whether to close (the door keeps scanning) */
export function scan(text: string, onText: (value: string) => boolean): void {
  shell!.scanned = onText;
  void native.call('scan', { text }).catch(() => {});
}
export const scanClose = (): void => { if (native.has('scan')) void native.call('scanClose').catch(() => {}); };

/** This iPhone's push token once the person allowed notifications (Apple's own prompt, once); { denied } once they
 *  turned them off in iOS Settings; null: not yet asked, or no token this time (nothing to change) */
export async function pushToken(): Promise<{ token: string } | { denied: true } | null> {
  if (!native.has('push')) return null;
  try { return await native.call<{ token: string } | { denied: true } | null>('push'); }
  catch { return null; }
}

/** sessionStorage key: the Telegram link this tab started (Settings), checked when Telegram sends it back (WebEntrance) */
export const TG_LINK = 'kb:telegram-link';

/** Telegram's #tgAuthResult (base64url JSON): the proof the server checks */
export const tgAuthResult = (b64: string): unknown =>
  JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0))));

/** Link Telegram in the iPhone app: Telegram's page in the system's sign-in sheet (ASWebAuthenticationSession; a page or
 *  popup inside the web view loses window.opener on iOS 17.5+), back through the server's /tg-back. The proof, or null
 *  when the sheet was closed or the return isn't this tap's (its state) */
export async function telegramProof(url: string, state: string): Promise<unknown> {
  let back: string | undefined;
  try { back = (await native.call<{ url: string } | null>('tglink', { url }))?.url; } catch { return null; }
  if (!back) return null;
  const u = new URL(back), m = u.hash.match(/tgAuthResult=([\w+/=-]+)/);
  return m && u.searchParams.get('state') === state ? tgAuthResult(m[1]) : null;
}

// ---- the native tab bar ('tabs'): the shell's UITabBar in place of ui/Nav.svelte's tabs (main.ts sets data-ntabs) ----
export interface NativeTab<T extends string> { id: T; title: string; dot: boolean }
let tabsNow: { items: NativeTab<string>[]; active: string; hidden: boolean } | null = null;
let tabsSent = '';
// the bar hides exactly when the web's own would: under a sheet (ui.svelte.ts hideChrome's data-sheet)
function sendTabs() {
  if (!tabsNow) return;
  const m = { ...tabsNow, hidden: tabsNow.hidden || document.documentElement.dataset.sheet != null };
  const s = JSON.stringify(m);
  if (s === tabsSent) return;
  tabsSent = s;
  void native.call('tabs', m).catch(() => {});
}
/** The tabs shown (in order, localized titles, dots), the active one, and whether the bar hides; a tap on the native bar
 *  comes back as onTab */
export function nativeTabs<T extends string>(items: NativeTab<T>[], active: T, hidden: boolean, onTab: (id: T) => void): void {
  if (!tabsNow) new MutationObserver(sendTabs).observe(document.documentElement, { attributes: true, attributeFilter: ['data-sheet'] });
  shell!.tab = (id) => { const k = items.find((x) => x.id === id); if (k) onTab(k.id); };
  tabsNow = { items, active, hidden };
  sendTabs();
}

// ---- offline tickets ('tickets'): what the door scans, kept by the shell for its offline screen ----
let ticketsSent = '';
function sendTickets(tickets: { title: string; at: number; place: string; qr: string }[], lang: string) {
  const s = JSON.stringify(tickets);
  if (s === ticketsSent) return;
  ticketsSent = s;
  void native.call('tickets', { tickets, lang }).catch(() => {});
}
/** My tickets still ahead, exactly what TicketView's QR encodes ('KBTU' + the code), with the title, time and place */
export function nativeTickets(events: EventCard[], lang: string): void {
  const now = Date.now() / 1000, seen = new Set<number>();
  sendTickets(events.filter((e) => {
    const ok = e.status !== 'cancelled' && e.my?.status === 'going' && !!e.my.ticketCode && !e.my.checkedInAt
      && (e.endsAt ?? e.startsAt + 6 * 3600) > now && !seen.has(e.id);
    seen.add(e.id);
    return ok;
  }).map((e) => ({ title: e.title, at: e.startsAt, place: e.place, qr: 'KBTU' + e.my!.ticketCode })), lang);
}
// signed out: the phone keeps none (the shell also clears them when the session cookie goes)
if (native.has('tickets')) addEventListener('kb:signedOut', () => sendTickets([], ''));
