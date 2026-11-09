// Navigation and overlays. One stack for every sheet and full-screen view: Telegram's Back button
// closes the top one (the prototype had a hand-written chain of 15 ifs for this).
import { untrack, type Component } from 'svelte';
import { haptic } from '../tg';
import { t } from '../i18n/index.svelte';
import { count, type Screen } from '../stats';
import { queue } from '../moments';
import { switching } from './theme.svelte';

export type Tab = 'afisha' | 'forum' | 'club' | 'profile';
// the forum second (Oct 30): the students' everyday place, next to the events
export const TABS: Tab[] = ['afisha', 'forum', 'club', 'profile'];
const NAV_KEY = 'kb-nav';

// one tab = one scrolling screen (Oct 30: the pages side by side in a tab were an 11-place grid even the owner got lost
// in); the tab and the club picked are kept across launches
function restore(): { tab: Tab; club: number | null } {
  try {
    const v = JSON.parse(localStorage.getItem(NAV_KEY) || 'null');
    if (v && TABS.includes(v.tab)) return { tab: v.tab, club: typeof v.club === 'number' ? v.club : null };
  } catch { /* blocked or corrupted */ }
  return { tab: 'afisha', club: null };
}

const start = restore();
export const ui = $state({
  tab: start.tab,
  club: start.club,        // the Clubs tab: the club picked in My club, the same on Team (null = the top one); kept across launches
  tryOn: null as { id: number; name: string; school?: boolean } | null, // a club's lanyard I'm not in, tried on in the settings: shown, never saved
  look: null as { skin: number | 'sower' | null; frame: string | null } | null, // my lanyard being edited in the settings (Me): shown, saved by the check
  busy: '',                // the capsule says this while a tap's work runs ("Making the link…"; no sign otherwise)
  gone: {} as Partial<Record<Tab, boolean>>, // a tab screen's large title has scrolled under the capsule (ui/title.ts)
  gate: false,             // the new policy's gate is up (App, ConsentGate): the app waits behind it
});

export function persistNav(): void {
  try { localStorage.setItem(NAV_KEY, JSON.stringify({ tab: ui.tab, club: ui.club })); } catch { /* blocked */ }
}
document.addEventListener('visibilitychange', () => { if (document.hidden) persistNav(); });

export function goTab(tab: Tab): void {
  if (ui.tab === tab) return;
  ui.tab = tab;
  haptic.select();
}

// ---- overlays ----
// eslint-disable-next-line @typescript-eslint/no-explicit-any
/** `title`: what the capsule says while this overlay is on top (SPEC §8.2); '' = the one below speaks. `theme`: the
 *  capsule's then, when the overlay has one of its own (the map's switch; the dark QR and ticket). `icon`: a small mark
 *  before the title for a full-screen mode (the QR, the map, the scanner, settings). `byUser`: the close came
 *  from a hand (Back, Escape, the scrim, a pull), not from the code after a save, so a sheet with typed text asks first. */
/** holdBack: Telegram's Back button waits while the overlay comes in (the map's iris, PLAN 80) */
/** feed: the Feed in a row, under it the nav and capsule take its dark tinted glass (chrome.ts) */
/** quiet: it has a large title of its own still in view (a Pane): the capsule shows the live status or nothing, and not
 *  the overlay below. mark: its title is in its own header (a Sheet's heading): the capsule shows its icon alone. */
export interface Overlay { id: number; component: Component<any>; props: Record<string, unknown>; closing: boolean; byUser?: boolean; title?: string; theme?: 'light' | 'dark'; icon?: Component<any>; holdBack?: boolean; feed?: boolean; quiet?: boolean; mark?: boolean;
  /** a tinted page (the event editor): its colour, which the sheets opened over it take (Sheet), and the capsule */
  tint?: string | null;
  /** what the anonymous counters call it (lib/stats.ts); a generic error toast is counted against the top one that has it */
  stat?: Screen }
export const overlays: Overlay[] = $state([]);
let seq = 0;

export function open<P extends Record<string, unknown>>(component: Component<P>, props: Omit<P, 'overlay'>, stat?: Screen): number {
  const id = ++seq;
  if (stat) count(stat);
  overlays.push({ id, component: component as Component<any>, props, closing: false, stat });
  return id;
}

/** Back with no overlay up: something on the tab itself to undo first (my badge turned to its QR side, Hero); its owner
 *  sets and clears it. Telegram's Back stays the only Back (AGENTS.md: One Back). */
export const backTo = $state<{ fn: (() => void) | null }>({ fn: null });

/** Ask the overlay to leave: it plays its exit animation, then calls removeOverlay(). No id: the top one, by a hand. */
export function close(id?: number, byUser = id == null): void {
  const o = id == null ? [...overlays].reverse().find((x) => !x.closing) : overlays.find((x) => x.id === id);
  if (o) { o.byUser = byUser; o.closing = true; }
}

/** While any sheet or full-screen overlay is up the nav hides; the capsule stays above it, says the top overlay's
 *  title and takes no taps (SPEC §8.2: it never disappears). Returns the undo. */
export function hideChrome(): () => void {
  const d = document.documentElement.dataset;
  d.sheet = String(Number(d.sheet || 0) + 1);
  return () => {
    const left = Number(d.sheet || 1) - 1;
    if (left > 0) d.sheet = String(left); else delete d.sheet;
  };
}

/** A moment nobody tapped for (the computer sheet, a roster sheet, an award): it opens only once nothing is open and
 *  the policy's gate is down, 600 ms after the last one (lib/moments.ts). A tap or a deep link opens at once. */
export const moment = queue(() => ui.gate || overlays.some((o) => !o.closing));

export function removeOverlay(id: number): void {
  const i = overlays.findIndex((x) => x.id === id);
  if (i >= 0) overlays.splice(i, 1);
}

// ---- toasts: live phrases with a 3D emoji ----
export const toast = $state<{ text: string; emoji: string; id: number; undo?: (() => void) | null }>({ text: '', emoji: 'party_popper_3d', id: 0 });
let toastTimer: ReturnType<typeof setTimeout> | undefined;
export function say(text: string, emoji = 'sparkles_3d', undo?: () => void): void {
  // a toast born mid-switch came solid and cleared up after (owner, Oct 31): it waits for the switch to end
  const vt = switching();
  if (vt) { vt.then(() => say(text, emoji, undo)); return; }
  untrack(() => { if (text === t('common.error')) count(`err.${[...overlays].reverse().find((o) => !o.closing && o.stat)?.stat ?? (`tab.${ui.tab}` as const)}`); });
  toast.text = text; toast.emoji = emoji; toast.undo = undo ?? null; toast.id++;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.text = ''), undo ? 5000 : 2600); // an Undo stays long enough to reach
}
