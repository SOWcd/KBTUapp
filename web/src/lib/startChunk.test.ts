// The start's JS stays light (issue 339): the entry script and every chunk index.html preloads with it, gzipped, under
// one limit. A new static import on the start path fails here; make it a lazy import or an idle warm-up (App.svelte),
// or raise the limit on purpose in the same PR. CI runs the tests before the build, so this builds in memory itself.
import { build, type Rollup } from 'vite';
import { afterEach, describe, expect, it, vi } from 'vitest';

/** Bytes of gzip (CompressionStream's level): 220,076 after issue 339 (227,870 before it), plus ~1.3% room. */
const MAX_START_GZIP = 223_000;

const gzipped = async (code: string) => (await new Response(new Blob([code]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer()).byteLength;

describe('the start chunk', () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  it(`is at most ${MAX_START_GZIP} bytes of gzipped JS`, async () => {
    vi.stubEnv('NODE_ENV', 'production'); // as `npm run build` makes it: vitest's NODE_ENV=test compiles Svelte's dev build
    const config = decodeURIComponent(new URL('../../vite.config.ts', import.meta.url).pathname);
    const out = await build({ configFile: config, mode: 'production', logLevel: 'silent', build: { write: false } });
    const files = new Map(([out].flat() as { output: (Rollup.OutputChunk | Rollup.OutputAsset)[] }[]).flatMap((o) => o.output).map((f) => [f.fileName, f]));
    const page = files.get('index.html');
    if (page?.type !== 'asset') throw new Error('no index.html in the build');
    // what the page loads before the app runs: the entry and its modulepreloads (never a lazy chunk)
    const start = [...String(page.source).matchAll(/<(?:script type="module"[^>]*\ssrc|link rel="modulepreload"[^>]*\shref)="\.\/([^"]+\.js)"/g)].map((m) => m[1]);
    expect(start.length).toBeGreaterThan(1);
    let gz = 0;
    for (const name of start) {
      const f = files.get(name);
      if (f?.type !== 'chunk') throw new Error(`${name} is not in the build`);
      gz += await gzipped(f.code);
    }
    console.log(`start JS: ${start.length} files, ${gz} B gzip (limit ${MAX_START_GZIP})`);
    expect(gz).toBeLessThanOrEqual(MAX_START_GZIP);
  }, 180_000);
});
