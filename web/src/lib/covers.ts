// A card's ground for a club with no lanyard of its own (the Clubs tab's recruiting badges): its logo's colours.
import type { OrgRef } from './api';
import { SvelteMap } from 'svelte/reactivity';
import { logoGradient, sample } from './color';
import { COVERS } from '../ui/OrgLogo.svelte';

// a logo's colours, read once and kept on the phone (a new logo has a new URL), so a card never flashes
const KEY = 'kb-logo-covers';
const kept: Record<string, string | null> = (() => { try { return JSON.parse(localStorage.getItem(KEY) ?? '{}'); } catch { return {}; } })();
const tints = new SvelteMap<string, string | null>(Object.entries(kept));
const reading = new Set<string>();
async function read(url: string) {
  if (reading.has(url)) return;
  reading.add(url);
  const px = await sample(url);
  const got = px && logoGradient(px);
  tints.set(url, got);
  if (!px) return; // a logo that failed is tried again next launch
  kept[url] = got;
  try { localStorage.setItem(KEY, JSON.stringify(kept)); } catch { /* blocked */ }
}

/** A card's background: the logo's colours, else the org's cover (an emoji-only org, a logo with no colour or one that
 *  won't read). Neutral for the moment a new logo is being read. */
export function coverOf(o: OrgRef): string {
  const plain = COVERS[o.cover % COVERS.length];
  if (!o.logo) return plain;
  const got = tints.get(o.logo);
  if (got === undefined) { void read(o.logo); return 'var(--text-3)'; }
  return got ?? plain;
}
