import { describe, expect, it, vi } from 'vitest';

vi.stubGlobal('document', { hidden: false, addEventListener: () => {} });
vi.stubGlobal('addEventListener', () => {});
vi.mock('./tg', () => ({ inTelegram: true, onIos: true, onAndroid: false, on: () => () => {}, tg: { initData: 'signed' } }));
const { bucketOf, count, flush, launchedFrom } = await import('./stats');

describe('usage counters', () => {
  it('keeps the class of a start parameter, never its value', () => {
    expect(['', 'ev_12_ABCDEFGHIJ', 'cl_3', 'fr_' + 'a'.repeat(24), 'r_ABCDEFGHIJ', 'ci_1_2_' + 'b'.repeat(16), 'friends'].map(launchedFrom))
      .toEqual(['from.none', 'from.event', 'from.club', 'from.friend', 'from.friend', 'from.qr', 'from.other']);
  });

  it('puts an open time in its bucket', () => {
    expect([999, 1000, 2999, 4999, 7999, 8000, 60000].map(bucketOf)).toEqual([0, 1, 2, 3, 4, 5, 5]);
  });

  it('adds up in memory, sends once, and a failure is dropped', () => {
    const send = vi.fn((_u: string, _o: { body: string }) => Promise.reject(new Error('down')));
    vi.stubGlobal('fetch', send);
    count('tab.afisha'); count('tab.afisha'); count('do.qr');
    flush(); flush();
    expect(send).toHaveBeenCalledTimes(1);
    expect(JSON.parse(send.mock.calls[0][1].body)).toEqual({ 'tab.afisha': 2, 'do.qr': 1 });
  });
});
