// The iPhone app's bridge (ios/KBTUApp/Bridge.swift). The shell puts window.kbNative = { v, caps } in before any
// script and answers messageHandlers.kb with a promise. A plain browser and Telegram have neither: has() is false and
// every caller keeps its web way. v is the bridge's version: a new capability or a changed message bumps it on both
// sides, and the web checks the capability, never the version, so an old app keeps working with a new web.
type Cap = 'apple' | 'push' | 'scan';
interface Shell { v: number; caps: string[]; scanned?: (text: string) => boolean }
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

/** This iPhone's push token once the person allowed notifications (Apple's own prompt, once), else null */
export async function pushToken(): Promise<string | null> {
  if (!native.has('push')) return null;
  try { return (await native.call<{ token: string } | null>('push'))?.token ?? null; }
  catch { return null; }
}
