import { describe, expect, it } from 'vitest';
import made from '../../tools/scene-rasters.json';

// The card draws its layers as pictures made from the SVGs, the picker its minis made from the card's components
// (tools/scene-rasters.mjs). A source changed without making its pictures again would leave the old art on screen: each
// hash here is the one its pictures were made from.
const SVGS = import.meta.glob(['/src/assets/lanyards/{scenes,schools,sower}/*-card.svg', '/src/assets/lanyards/{kbtu-rosette,kbtu-facade}.svg'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const PICS = import.meta.glob('/src/assets/lanyards/**/*.webp', { query: '?url', import: 'default', eager: true }) as Record<string, string>;
const ALL_SVG = import.meta.glob('/src/assets/lanyards/**/*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const MINI_SRC = ['/src/ui/LanyardBand.svelte', '/src/ui/ClubScene.svelte', '/src/ui/SchoolScene.svelte', '/src/ui/KbtuMark.svelte', '/src/lib/awards.ts', '/tools/minis/Minis.svelte'];
const CODE = import.meta.glob(['/src/ui/{LanyardBand,ClubScene,SchoolScene,KbtuMark}.svelte', '/src/lib/awards.ts', '/tools/minis/Minis.svelte'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

describe('lanyard pictures', () => {
  it('every card layer has its picture, made from the SVG as it is now', async () => {
    const { createHash } = await import('node:crypto' as string); // no @types/node here (design.test.ts)
    const want = made as Record<string, string>;
    for (const [path, src] of Object.entries(SVGS)) {
      const f = path.replace('/src/assets/lanyards/', '');
      expect(PICS[path.replace(/\.svg$/, '.webp')], `${f}: no picture, run node tools/scene-rasters.mjs`).toBeTruthy();
      expect(createHash('sha1').update(src).digest('hex').slice(0, 12), `${f} changed: run node tools/scene-rasters.mjs`).toBe(want[f]);
    }
  });
  it("the picker's minis are made from the lanyards as they are now", async () => {
    const { createHash } = await import('node:crypto' as string);
    const h = createHash('sha1');
    for (const f of MINI_SRC) h.update(CODE[f]);
    for (const f of Object.keys(ALL_SVG).sort()) h.update(ALL_SVG[f]);
    expect(h.digest('hex').slice(0, 12), 'a lanyard changed: run node tools/scene-rasters.mjs').toBe((made as Record<string, string>).minis);
  });
});
