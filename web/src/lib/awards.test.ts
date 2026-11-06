// A card the app only partly knows yet (opened from a friend row before the server answers) shows no numbers rather
// than wrong zeros; the full card shows all three.
import { expect, it, vi } from 'vitest';

// awards.ts reads the clubs for a lanyard (lookOf); the real state pulls in the DOM
vi.mock('./state/data.svelte', () => ({ data: { orgs: [] } }));
import { artOf, isCoin, isMedal, layersOf, legendOf, hero, splitVariants, ZNAKI, QR_LOOK, CLUB_LOOKS, SCHOOL_LOOKS, MANUAL, awardOf, codesOf } from './awards';
import type { PersonCard } from './api';

const card = (attended: number): PersonCard => ({ id: 7, name: 'Ali T.', avatar: null, founder: false, no: 6, course: 2, school: 'SITE', bio: '', attended, past: [],
  clubs: [], showcase: [], shelf: [], awards: { achievements: [], badges: [] }, friendship: 'friends', friendsSince: 1, going: [] });

it('hides the numbers of a card it only partly knows', () => {
  expect(hero(card(-1)).loaded).toBe(false);
  expect(hero(card(3))).toMatchObject({ loaded: true, earned: 0, total: 0, next: null });
});

it('shows the card number zero-padded, a dash while there is none', () => {
  expect(hero(card(0)).no).toBe('00006');
  expect(hero({ ...card(0), founder: true, no: 0 }).no).toBe('00000');
  expect(hero({ ...card(0), no: null }).no).toBe('—');
});

it('puts DMP, then the Student Government, before a higher role in a club on the lanyard', () => {
  const org = (id: number, extra: object) => ({ id, slug: `o${id}`, name: `Org ${id}`, short: `O${id}`, emoji: 'x', cover: 0, kind: 'club', official: false, ...extra });
  const c = card(1);
  c.clubs = [{ org: org(1, {}), role: 'head', title: 'Head of Events' }, { org: org(2, { gov: true }), role: 'member', title: 'Minister' }] as PersonCard['clubs'];
  expect(hero(c).title).toBe('Minister · Org 2');
  c.clubs = [...c.clubs, { org: org(3, { kind: 'office' }), role: 'member', title: null }] as PersonCard['clubs'];
  expect(hero(c).title).toMatch(/· Org 3$/);
});

it("Recruiter's medal is drawn per level", () => {
  const lv = Array.from({ length: 9 }, (_, i) => ({ need: i + 1, share: 0 }));
  const of = (level: number) => artOf({ code: 'referral', emoji: 'megaphone_3d', level, levels: lv as never });
  expect([0, 1, 4, 9].map(of)).toEqual(['layer_rc1', 'layer_rc1', 'layer_rc4', 'layer_rc9']);
  expect(layersOf(of(4))?.map(([n]) => n)).toEqual(['rc-field-s', 'rc-net-4', 'rc-core-s', 'rc-rim-s']);
  // the others: one picture, the rim the level's metal; the one-time ones are pins, not medals
  expect(layersOf(artOf({ code: 'soul', emoji: 'raising_hands_3d_default', level: 2, levels: lv.slice(0, 4) as never }))?.map(([n]) => n))
    .toEqual(['so-field', 'so-art-s', 'so-near-s', 'md-rim-s']);
  expect(artOf({ code: 'critic', emoji: 'x', level: 7, levels: lv.slice(0, 7) as never })).toBe('layer_cr_l');
  expect(isMedal({ code: 'anthem', levels: lv.slice(0, 1) as never })).toBe(false);
  expect(isMedal({ code: 'bugs', levels: lv.slice(0, 1) as never })).toBe(true); // Admin's row of a manual one
  // the 2026 initiation's coins stay the owner's drawn pictures, among the pins
  expect([isCoin({ emoji: 'medal_init26p_2' }), isCoin({ emoji: 'medal_first500' }), isMedal({ code: 'init26', levels: lv.slice(0, 1) as never })]).toEqual([true, true, false]);
});

it('every medal layer and pin glyph is drawn', async () => {
  const fs = await import('node:fs' as string);
  const has = (n: string) => fs.existsSync(new URL(`../../public/medals/${n}.svg`, import.meta.url));
  const lv = Array.from({ length: 9 }, (_, i) => ({ need: i + 1, share: 0 }));
  for (const code of ['regular', 'streak', 'soul', 'team', 'season', 'bugs', 'critic', 'referral'])
    for (const n of [1, 4, 7]) {
      const art = artOf({ code, emoji: '', level: n, levels: lv.slice(0, 7) as never }), leg = legendOf(art);
      expect(layersOf(art)!.every(([f]) => has(f)) && (code === 'referral' ? leg === null : has(leg!))).toBe(true);
    }
  // the temporary vector set (VECTOR in awards.ts): First in and the creator's two
  for (const art of ['layer_vb_firstin', 'layer_vb_laugh', 'layer_vb_hello']) expect(layersOf(art)!.every(([f]) => has(f))).toBe(true);
  for (const z of Object.values(ZNAKI)) expect(layersOf(`layer_zn_${z.glyph}_${z.metal}`)!.every(([n]) => has(n)) && has('zn-enamel') && has(`zn-frame-${z.metal}`)).toBe(true);
  for (const m of 'bsgl') expect(has(`ribbon-${m}`)).toBe(true);
});

it('a badge held in two variants shows both', () => {
  const a = { code: 'init26', emoji: 'medal_init26p_2', variant: 'init26p', level: 1, variants: [
    { code: 'init26p', emoji: 'medal_init26p_2', have: true, rarity: 0.01 }, { code: 'init26', emoji: 'medal_init26_2', have: true, rarity: 0.05 },
    { code: 'init26f', emoji: 'medal_init26f_2', have: false, rarity: 0.3 }] } as never;
  expect(splitVariants([a]).map((x) => [x.variant, x.emoji])).toEqual([['init26p', 'medal_init26p_2'], ['init26', 'medal_init26_2']]);
});

it("every club's and school's lanyard QR ink reads on the white plate (>= 7:1)", () => {
  const lum = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const low = [...Object.keys(CLUB_LOOKS), ...Object.keys(SCHOOL_LOOKS)].flatMap((k) => QR_LOOK[k as keyof typeof QR_LOOK]!.filter((c) => 1.05 / (lum(c) + 0.05) < 7).map((c) => `${k} ${c}`));
  expect(low).toEqual([]);
});

// Admin → Awards: one entry per award; a badge's grant codes are its variants, never the award's own code alone
it('lists a badge once, its variants inside', () => {
  expect(MANUAL.map((a) => a.code)).toEqual(['creator_laugh', 'creator_found', 'bugs', 'init26']);
  expect(codesOf(MANUAL[3])).toEqual(['init26p', 'init26', 'init26f']);
  expect(codesOf(MANUAL[2])).toEqual(['bugs']);
  for (const c of ['init26p', 'init26', 'init26f']) expect(awardOf(c).code).toBe('init26'); // a held Performer or Guest holds it
  expect(MANUAL.flatMap(codesOf)).toEqual(['creator_laugh', 'creator_found', 'bugs', 'init26p', 'init26', 'init26f']);
});
