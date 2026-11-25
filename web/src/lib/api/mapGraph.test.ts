import { expect, it, vi } from 'vitest';

vi.mock('../awards', () => ({ splitVariants: vi.fn() }));
vi.mock('../tg', () => ({ tg: { initData: '' } }));
vi.mock('../state/recovery', () => ({ accountClosed: () => false, accountRequest: () => new AbortController().signal }));
vi.mock('../state/sheets', () => ({ sheets: {} }));
vi.mock('../i18n/index.svelte', () => ({ i18n: { lang: 'en' } }));
import { server } from './client';

it('shares a map graph read, retries a failure and reuses the loaded graph', async () => {
  const graph = { n: [], e: [], ver: 0 };
  const fetch = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(Response.json(graph));
  vi.stubGlobal('window', {});
  vi.stubGlobal('fetch', fetch);
  try {
    const failed = server.mapGraph();
    expect(server.mapGraph()).toBe(failed);
    await expect(failed).rejects.toThrow('network');
    const loaded = server.mapGraph();
    expect(server.mapGraph()).toBe(loaded);
    await expect(loaded).resolves.toEqual(graph);
    expect(server.mapGraph()).toBe(loaded);
    expect(fetch).toHaveBeenCalledTimes(2);
  } finally { vi.unstubAllGlobals(); }
});
