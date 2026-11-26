import { afterEach, expect, it, vi } from 'vitest';
import type { Component } from 'svelte';

vi.stubGlobal('document', { addEventListener: () => {} });
vi.mock('../stats', () => ({ count: vi.fn(), timed: vi.fn() }));
vi.mock('../tg', () => ({ onShareBusy: () => {}, tg: { initData: '' } }));
vi.mock('./theme.svelte', () => ({ switching: () => null }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k }));
const { open, close, overlays, removeOverlay } = await import('./ui.svelte');
const club: Component = () => ({});
const assistant: Component = () => ({});

afterEach(() => { overlays.splice(0); });

it('returns to an existing sheet and leaves the intervening sheets mounted until their exits finish', () => {
  const first = open(club, { id: 1 });
  const original = open(club, { id: 2, seed: 'original' });
  const ask = open(assistant, {}, undefined, 'club:2');
  const other = open(club, { id: 3 });
  close(other);

  expect(open(club, { id: 2, seed: 'new' })).toBe(original);
  expect(overlays.map((o) => [o.id, o.closing])).toEqual([[first, false], [original, false], [ask, true], [other, true]]);
  expect(overlays[1].props.seed).toBe('original');
  removeOverlay(other);
  removeOverlay(ask);
  close();
  expect(overlays.map((o) => [o.id, o.closing])).toEqual([[first, false], [original, true]]);
});

it('keeps different kinds, ids and view modes distinct', () => {
  const original = open(club, { id: 2 });
  const ask = open(assistant, { id: 2 });
  const other = open(assistant, { id: 3 });
  const preview = open(club, { id: 2 }, undefined, 'preview:2');

  expect(overlays.map((o) => o.id)).toEqual([original, ask, other, preview]);
  expect(open(club, { id: 2 }, undefined, 'preview:2')).toBe(preview);
  expect(overlays.every((o) => !o.closing)).toBe(true);
});

it('allows a fresh open after Back starts an exit', () => {
  const leaving = open(club, { id: 2 });
  close();
  const opened = open(club, { id: 2 });

  expect(opened).not.toBe(leaving);
  removeOverlay(leaving);
  expect(overlays.map((o) => o.id)).toEqual([opened]);
});
