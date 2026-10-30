// Every translation asks for the same holes as the Russian source ({name}, {n}…): a hole only one language has would
// show up as raw braces for the people reading it.
import { expect, it } from 'vitest';
import ru from './ru';
import kk from './kk';
import en from './en';

const holes = (v: unknown): string => [...new Set(JSON.stringify(v).match(/\{[a-zA-Z]+\}/g) ?? [])].sort().join(',');

it('keeps the same holes in ru, kk and en', () => {
  const bad: string[] = [];
  for (const [k, v] of Object.entries(ru)) for (const [name, d] of [['kk', kk], ['en', en]] as const) {
    if (holes(v) !== holes((d as Record<string, unknown>)[k])) bad.push(`${name} ${k}`);
  }
  expect(bad).toEqual([]);
});

// A word too long for its line on a 320-px phone (a 34-px title shrunk to 24, a 17-px row) breaks at its soft hyphen
// (U+00AD) with a visible hyphen, never anywhere: WebKit has no Kazakh hyphenation. Every Russian and Kazakh word of
// 15 letters or more carries at least one, at a syllable or morpheme joint.
it('puts a soft hyphen in every long ru and kk word', () => {
  const words = (d: Record<string, unknown>) => Object.values(d)
    .flatMap((v) => (typeof v === 'string' ? [v] : Object.values(v as Record<string, string>)))
    .flatMap((s) => s.match(/[\p{L}­]{15,}/gu) ?? [])
    .filter((w) => w.replace(/­/g, '').length >= 15 && !w.includes('­'));
  expect([...words(ru), ...words(kk)]).toEqual([]);
});
