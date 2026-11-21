import { recovery, SCREEN_AGE } from './recovery';

// Only named destinations may enter a checkpoint. The live overlay stack holds components and callbacks.
export const TABS = ['afisha', 'forum', 'club', 'profile'] as const;
export type Tab = typeof TABS[number];
export type Place = { kind: 'event' | 'club' | 'post' | 'postComments'; id: number; org?: number };
export type ScrollAnchor = { top: number; item?: string; offset?: number };
export interface Navigation { tab: Tab; club: number | null; scroll: ScrollAnchor; sheet: Place | null }

const NAV = 'kb-nav';
const id = (n: unknown): n is number => typeof n === 'number' && Number.isSafeInteger(n) && n > 0;
function place(p: Place | null): Place | null {
  if (!p || !id(p.id)) return null;
  if (p.kind === 'event' || p.kind === 'club' || p.kind === 'postComments') return { kind: p.kind, id: p.id };
  return p.kind === 'post' && id(p.org) ? { kind: p.kind, id: p.id, org: p.org } : null;
}
export function readNavigation(store = recovery, scope = store.scope()): Navigation | null {
  const n = store.newest<Navigation>(scope, NAV, SCREEN_AGE);
  if (!n || !TABS.includes(n.tab)) return null;
  const top = n.scroll?.top;
  const scroll: ScrollAnchor = { top: Number.isFinite(top) && top > 0 ? top : 0 };
  if (typeof n.scroll?.item === 'string' && /^[a-z]+-\d+$/.test(n.scroll.item) && Number.isFinite(n.scroll.offset)) {
    scroll.item = n.scroll.item;
    scroll.offset = n.scroll.offset;
  }
  return { tab: n.tab, club: id(n.club) ? n.club : null, scroll, sheet: place(n.sheet) };
}

export function checkpoint(write: (json: string) => void, initial: Navigation | null) {
  let last = initial ? JSON.stringify(initial) : '';
  return (nav: Navigation) => {
    const json = JSON.stringify(nav);
    if (json === last) return; // mounting or hiding a copy is not a navigation change
    last = json;
    write(json);
  };
}
export const keepNavigation = (scope: string | null, initial: Navigation | null) =>
  checkpoint((json) => recovery.writeCheckpoint(scope, NAV, json), initial);

export function launchNavigation(start: string, microsoftReturn: boolean, read = readNavigation): Navigation | null {
  return start || microsoftReturn ? null : read();
}
