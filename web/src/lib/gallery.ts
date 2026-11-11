// The Gallery's feed as it is drawn: stretches of time ("Today", "Yesterday", "This week", then a month), each a set of
// justified rows. Pure: Gallery.svelte draws what this returns.
import type { AlbumPhoto } from './api';
import { t } from './i18n/index.svelte';
import { dayNo, monthName, nowTs, parts } from './time';

export type Tile = { p: AlbumPhoto; i: number; ar: number }; // i: its place in the whole list (the viewer's)
export type Row = { tiles: Tile[]; lead?: boolean };
export type Group = { key: string; label: string; rows: Row[] };

const shape = (p: AlbumPhoto) => (p.w && p.h ? Math.min(2.2, Math.max(0.66, p.w / p.h)) : 1);

function stretch(at: number, now: number): [string, string] {
  const d = dayNo(now) - dayNo(at), p = parts(at);
  if (d <= 0) return ['today', t('common.today')];
  if (d === 1) return ['yesterday', t('gallery.day.yesterday')];
  if (d < 7) return ['week', t('gallery.day.week')];
  return [`${p.y}-${p.m}`, monthName(at) + (p.y === parts(now).y ? '' : ' ' + p.y)];
}

/** Rows of one, two or three photos, each photo taking width by its own shape. Three only for three portraits (or the
 *  last three, so no photo ends alone), never twice running; else a pair, two wide ones cut to 4:3 so the row still
 *  stands tall enough for its captions; a panorama (16:9 and wider) keeps a row to itself, and so does the last odd one,
 *  cut to 4:3 at the tallest (the viewer shows the original). lead: the first one full width, 3:2. */
export function justify(tiles: Tile[], lead = false): Row[] {
  const out: Row[] = [];
  let i = 0;
  if (lead && tiles.length) out.push({ tiles: [{ ...tiles[i++], ar: 1.5 }], lead: true });
  while (i < tiles.length) {
    const a = tiles[i], b = tiles[i + 1], c = tiles[i + 2], left = tiles.length - i;
    const sum3 = c ? a.ar + b.ar + c.ar : 9;
    if (c && out[out.length - 1]?.tiles.length !== 3 && ((a.ar < 1 && b.ar < 1 && c.ar < 1 && sum3 <= 2.7) || (left === 3 && sum3 <= 3))) { out.push({ tiles: [a, b, c] }); i += 3; }
    else if (b && a.ar < 1.7 && b.ar < 1.7) {
      const cut = a.ar + b.ar > 2.7 ? 1.35 : 9;
      out.push({ tiles: [{ ...a, ar: Math.min(a.ar, cut) }, { ...b, ar: Math.min(b.ar, cut) }] });
      i += 2;
    } else { out.push({ tiles: [{ ...a, ar: Math.max(a.ar, 4 / 3) }] }); i++; }
  }
  return out;
}

/** The list (newest first) by stretches of time. Mine still uploading is of today. A photo with no time (the albums'
 *  where posting is off for me: the feed says no more than the album) sits in its newer neighbour's stretch; none with a
 *  time at all: one set, no header. */
export function groups(photos: AlbumPhoto[], now = nowTs()): Group[] {
  const out: { key: string; label: string; tiles: Tile[] }[] = [];
  let early: Tile[] = []; // before the first one with a time
  photos.forEach((p, i) => {
    const at = p.at ?? (p.pending || p.failed ? now : null), tile = { p, i, ar: shape(p) }, last = out[out.length - 1];
    if (at == null) { (last?.tiles ?? early).push(tile); return; }
    const [key, label] = stretch(at, now);
    if (last?.key.startsWith(key + ':')) last.tiles.push(tile);
    else { out.push({ key: `${key}:${p.id}`, label, tiles: [...early, tile] }); early = []; }
  });
  if (early.length) out.push({ key: 'all', label: '', tiles: early }); // no time anywhere: one quiet set
  return out.map((g, n) => ({ key: g.key, label: g.label, rows: justify(g.tiles, n === 0) }));
}
