// Openers for the sheets that are reachable from anywhere (any avatar opens the profile card, any
// event row opens the event). Each is written once, in openers.ts (it fills `sheets` as it loads; App imports it), or
// for the few that need App's state or its components, in App.svelte; components call these, so no import cycles.
// This module imports types only: ui.svelte.ts imports it, and so do the unit tests that run without a window.
import type { EventCard, Id, LinkCard } from '../api';
import type { AskCtx } from './assistant.svelte';
import type { openers } from './openers';
import type { Overlay } from './ui.svelte';

export type SheetKey = number | string;

/** A closing entry stays mounted for its exit. Return to the live entry without changing its props or scroll. */
export function returnToSheet(stack: Overlay[], component: Overlay['component'], key: SheetKey, close: (id: number) => void): number | undefined {
  const at = stack.findIndex((o) => !o.closing && o.component === component && o.key === key);
  if (at < 0) return;
  for (const o of stack.slice(at + 1).reverse()) if (!o.closing) close(o.id);
  return stack[at].id;
}

// wait: ms before "ok" can be tapped (a second confirm, so a double tap doesn't go through both)
export type Ask = { title: string; text?: string; ok: string; cancel: string; danger?: boolean; wait?: number; link?: { label: string; url: string } };
export type InviteLanding = { code: string; card: LinkCard; alreadyRegistered: boolean };

/** a still copy of the top capsule and its theme wrapper's classes (the map's circle cuts between it and the live one) */
export type CapCopy = { node: HTMLElement; theme: string };
export function copyCap(): CapCopy | null {
  const c = document.querySelector<HTMLElement>('.cap');
  if (!c) return null;
  const node = c.cloneNode(true) as HTMLElement;
  node.removeAttribute('role');
  return { node, theme: c.parentElement?.className ?? '' };
}
/** where the map was opened from (the nav's round button): it opens out of that circle and closes back into it, and
 *  the capsule as it was before the map changed it */
export const mapFrom: { at: { x: number; y: number; r: number } | null; cap: CapCopy | null; el: HTMLElement | null } = { at: null, cap: null, el: null };
/** The iris: a screen opens out of the round button that was pressed (the map's opening, more often).
 *  The opener marks its place on the click; whichever Sheet, Pane or Feed mounts next takes it, once, if still fresh. */
type Iris = { x: number; y: number; r: number; el?: HTMLElement /* the control itself (the assistant's light hides it while it flies) */ };
let irisAt: (Iris & { t: number }) | null = null;
export function irisFrom(e: MouseEvent) {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  irisAt = { x: r.left + r.width / 2, y: r.top + r.height / 2, r: Math.min(r.width, r.height) / 2, el: e.currentTarget as HTMLElement, t: performance.now() };
}
/** the mark, left for whoever takes it (the assistant's light flies out of the same place the Sheet's circle opens from) */
export const peekIris = (): Iris | null =>
  irisAt && performance.now() - irisAt.t < 1500 && !matchMedia('(prefers-reduced-motion: reduce)').matches ? irisAt : null;
export function takeIris(): Iris | null {
  const i = peekIris(); irisAt = null;
  return i;
}
/** the circle opening over `el`, already in its place; clip-path only, the screen under it is painted once */
export function irisOpen(el: HTMLElement, i: Iris): Animation {
  const b = el.getBoundingClientRect(), x = i.x - b.left, y = i.y - b.top;
  const far = Math.hypot(Math.max(x, b.width - x), Math.max(y, b.height - y));
  return el.animate({ clipPath: [`circle(${i.r}px at ${x}px ${y}px)`, `circle(${far}px at ${x}px ${y}px)`] }, { duration: 520, easing: 'cubic-bezier(.32, .8, .3, 1)' });
}
/** ...and closing back into the place it opened from (Sheet `shut`): the same circle the other way, eased out at its end
 *  as the map's (an ease-in close "hit like a hammer"), gone in its last third */
export function irisShut(el: HTMLElement, i: Iris): Animation {
  const b = el.getBoundingClientRect(), x = i.x - b.left, y = i.y - b.top;
  const far = Math.hypot(Math.max(x, b.width - x), Math.max(y, b.height - y));
  return el.animate({ clipPath: [`circle(${far}px at ${x}px ${y}px)`, `circle(${i.r}px at ${x}px ${y}px)`], opacity: [1, 1, 0] },
    { duration: 440, easing: 'cubic-bezier(.45, 0, .2, 1)', fill: 'forwards' });
}
/** open the map out of the control that was pressed (the iris), wherever that control lives */
export function openMapFrom(e: MouseEvent) {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  mapFrom.at = { x: r.left + r.width / 2, y: r.top + r.height / 2, r: Math.min(r.width, r.height) / 2 };
  mapFrom.cap = copyCap();
  mapFrom.el = e.currentTarget as HTMLElement; // it closes back into this very control (CampusMap leave)
  sheets.map();
}

/** The door screen: the event's QR and the scanner on this phone, one switch apart (Scanner.svelte).
 *  A member's QR: an ordinary public event only, never the volunteers ledger's club `vol` (server checkin._guests:
 *  those scans count hours and misses), so there the scanner has no switch. runs: its organizers. */
export function registration(e: EventCard, runs: boolean, vol?: Id): void {
  sheets.scanner(e.id, false, !e.guestHost && (runs || (!e.meeting && e.visibility !== 'members' && e.visibility !== 'leaders' && e.org.id !== vol)));
}

// App's own (App.svelte sets them): no-ops until it does
const own = {
  login: (_after?: () => void, _lock?: boolean) => {}, // its LoginSheet, one at a time
  assistant: (_ctx?: AskCtx) => {},      // the students' assistant (with the forum's switch); ctx: asked from that card
  /** the server says the policy changed (a refused write): the fresh /api/me raises the gate (ConsentGate) */
  consent: () => {},
  /** a new achievement level just earned in a sheet that stays open (the anthem's): its unlock moment now, over it */
  celebrate: () => {},
  registry: () => {}, // DMP's whole registry in a sheet (for the admin); App notes it opened in this launch (lib/desk.ts)
  /** In-app confirmation (never a system dialog); resolves true on "ok". */
  ask: (_q: Ask): Promise<boolean> => Promise.resolve(false),
  /** the same with a few words to write (a meeting's "Can't make it": why); null = cancelled. tel: a phone number instead,
   *  handed over as +7XXXXXXXXXX; value: filled in to edit; line: one line, Enter answers (a nick) */
  askText: (_q: Ask & { placeholder: string; max: number; tel?: boolean; value?: string; line?: boolean }): Promise<string | null> => Promise.resolve(null),
  /** our own t.me link's startapp, opened as if tapped (App.deepLink): a scanner that read one of our QRs */
  deepLink: (_p: string) => {},
};
export const sheets = own as typeof own & typeof openers;
