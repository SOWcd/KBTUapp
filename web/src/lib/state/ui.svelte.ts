// Navigation and overlays. One stack for every sheet and full-screen view: Telegram's Back button
// closes the top one (the prototype had a hand-written chain of 15 ifs for this).
import type { Component } from 'svelte';
import { haptic } from '../tg';

export type Tab = 'afisha' | 'forum' | 'club' | 'profile';
// the forum second (Oct 30): the students' everyday place, next to the events
export const TABS: Tab[] = ['afisha', 'forum', 'club', 'profile'];
const NAV_KEY = 'kb-nav';
/** Each tab's home page: List, the forum, Studio (the catalogue for a non-member, clamped), Me. */
const HOME: Record<Tab, number> = { afisha: 1, forum: 0, club: 1, profile: 1 };
// away this long, each tab opens on its home page again (owner, Oct 29: the tabs kept their last page "forever" and even
// he got lost); the tab itself and the club picked stay
const AWAY = 10 * 60_000;

function restore(): { tab: Tab; page: Record<Tab, number>; club: number | null } {
  try {
    const v = JSON.parse(localStorage.getItem(NAV_KEY) || 'null');
    if (v && TABS.includes(v.tab) && v.page) {
      const fresh = typeof v.at === 'number' && Date.now() - v.at < AWAY;
      return { tab: v.tab, page: { ...HOME, ...(fresh ? v.page : {}) }, club: typeof v.club === 'number' ? v.club : null };
    }
  } catch { /* blocked or corrupted */ }
  return { tab: 'afisha', page: { ...HOME }, club: null };
}

const start = restore();
export const ui = $state({
  tab: start.tab,
  page: start.page,
  navMini: false,          // bottom nav shrinks to icons while scrolling down
  awake: 0,                // bumps on interaction: the capsule shows the page switcher for a moment
  club: start.club,        // tab 2: the club picked in Studio, the same on Team (null = the top one); kept across launches
  busy: '',                // the capsule says this while a tap's work runs ("Making the link…"; no sign otherwise)
});

export function persistNav(): void {
  try { localStorage.setItem(NAV_KEY, JSON.stringify({ tab: ui.tab, page: ui.page, club: ui.club, at: Date.now() })); } catch { /* blocked */ }
}
// Telegram keeps a Mini App alive in the background: coming back after AWAY is a fresh start too
let hiddenAt = 0;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { hiddenAt = Date.now(); persistNav(); }
  else if (hiddenAt && Date.now() - hiddenAt > AWAY) Object.assign(ui.page, HOME);
});

export function goTab(tab: Tab): void {
  if (ui.tab === tab) { ui.page[tab] = HOME[tab]; return; } // re-tap: back to the tab's home page
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
export interface Overlay { id: number; component: Component<any>; props: Record<string, unknown>; closing: boolean; byUser?: boolean; title?: string; theme?: 'light' | 'dark'; icon?: Component<any>; holdBack?: boolean }
export const overlays: Overlay[] = $state([]);
let seq = 0;

export function open<P extends Record<string, unknown>>(component: Component<P>, props: Omit<P, 'overlay'>): number {
  const id = ++seq;
  overlays.push({ id, component: component as Component<any>, props, closing: false });
  return id;
}

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

export function removeOverlay(id: number): void {
  const i = overlays.findIndex((x) => x.id === id);
  if (i >= 0) overlays.splice(i, 1);
}

// ---- toasts: live phrases with a 3D emoji ----
export const toast = $state({ text: '', emoji: 'party_popper_3d', id: 0 });
let toastTimer: ReturnType<typeof setTimeout> | undefined;
export function say(text: string, emoji = 'sparkles_3d'): void {
  toast.text = text; toast.emoji = emoji; toast.id++;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.text = ''), 2600);
}
