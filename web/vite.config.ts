import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliCompressSync, constants, gzipSync } from 'node:zlib';
import { defineConfig, type Plugin } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// What the first screen needs is asked for with the HTML, not after the bundle runs: Inter's latin and cyrillic files
// (the CSS names them only once it is parsed) and a Kazakh or English student's language chunk (main.ts waits for it
// before the first render). The URLs carry the build's hashes, so they are written in at build time.
function preloads(): Plugin {
  return {
    name: 'kb-preloads',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(_html, ctx) {
        const files = Object.keys(ctx.bundle ?? {});
        const find = (re: RegExp) => files.find((f) => re.test(f));
        const fonts = [/inter-latin-opsz-normal.*\.woff2$/, /inter-cyrillic-opsz-normal.*\.woff2$/].map(find);
        const langs = { kk: find(/^assets\/kk-[\w-]+\.js$/), en: find(/^assets\/en-[\w-]+\.js$/) };
        if (fonts.includes(undefined) || !langs.kk || !langs.en) throw new Error('kb-preloads: a font or a language chunk was not found');
        // the language as i18n's detect() picks it: the kept choice, else Telegram's (from the launch URL: the SDK
        // isn't loaded yet); Russian is in the bundle
        const pick = `(function () {
  var urls = ${JSON.stringify(langs)}, l = null;
  try { l = localStorage.getItem('kb-lang'); } catch (e) {}
  if (!l) try { l = JSON.parse(new URLSearchParams(new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || '').get('user') || '{}').language_code; } catch (e) {}
  l = (l || '').slice(0, 2);
  if (!urls[l]) return;
  var k = document.createElement('link'); k.rel = 'modulepreload'; k.crossOrigin = ''; k.href = './' + urls[l]; document.head.appendChild(k);
})();`;
        return [
          ...fonts.map((f) => ({ tag: 'link', attrs: { rel: 'preload', as: 'font', type: 'font/woff2', href: './' + f, crossorigin: '' }, injectTo: 'head' as const })),
          { tag: 'script', children: pick, injectTo: 'head' as const },
        ];
      },
    },
  };
}

// The sheets a tap opens anywhere and the map are chunks. V8 compiles a function only on its first call,
// so the first open of each paid for compiling the whole sheet inside the tap (~40 ms at 4x CPU of a ~140 ms task).
// Chrome's explicit compile hint has them compiled as the chunk loads, ahead of the tap; other engines ignore the line.
function compileHints(names: RegExp): Plugin {
  return {
    name: 'kb-compile-hints',
    apply: 'build',
    generateBundle(_o, bundle) {
      for (const c of Object.values(bundle)) if (c.type === 'chunk' && names.test(c.name)) c.code = '//# allFunctionsCalledOnLoad\n' + c.code;
    },
  };
}

// The hashed text files under assets/ written once more as .br and .gz, at the strongest levels: the server sends the
// ready one (app.py file()) instead of gzipping the same bundle on its event loop for every new client, and brotli is
// smaller still. Only text, and only what compression pays for.
function precompress(): Plugin {
  return {
    name: 'kb-precompress',
    apply: 'build',
    writeBundle(opts, bundle) {
      for (const [name, out] of Object.entries(bundle)) {
        if (!/^assets\/.+\.(js|css|svg|json)$/.test(name)) continue;
        const raw = Buffer.from(out.type === 'chunk' ? out.code : out.source);
        if (raw.length < 1024) continue;
        const file = join(opts.dir!, name);
        writeFileSync(file + '.br', brotliCompressSync(raw, { params: { [constants.BROTLI_PARAM_QUALITY]: 11, [constants.BROTLI_PARAM_SIZE_HINT]: raw.length } }));
        writeFileSync(file + '.gz', gzipSync(raw, { level: 9 }));
      }
    },
  };
}

// every lucide icon renders through our ui/LucideIcon.svelte: the same SVG, a third of a tab's build time less
function lucideIcon(): Plugin {
  const to = fileURLToPath(new URL('./src/ui/LucideIcon.svelte', import.meta.url));
  return {
    name: 'kb-lucide-icon',
    enforce: 'pre',
    resolveId(source, importer) {
      if (source === '../Icon.svelte' && importer && /[\\/]@lucide[\\/]svelte[\\/]dist[\\/]icons[\\/]/.test(importer)) return to;
    },
  };
}

export default defineConfig({
  // relative URLs: the same build works at kbtu.sow.kz/ and under a sub-path like /next/
  base: './',
  plugins: [lucideIcon(), svelte(), preloads(), compileHints(/^(EventSheet|PersonSheet|ClubSheet|CampusMap)$/), precompress()],
  server: { host: true, port: 5180 },
  // not prebundled in dev, so the dev server's icons go through ui/LucideIcon.svelte too (plugins don't run in a prebundle)
  optimizeDeps: { exclude: ['@lucide/svelte'] },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // iOS 15 still runs Telegram; syntax is lowered for it, the app stays modern otherwise
    target: ['es2020', 'safari15', 'chrome100'],
    assetsInlineLimit: 0,
  },
});
