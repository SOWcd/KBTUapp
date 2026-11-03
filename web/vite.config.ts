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

// The sheets a tap opens anywhere are chunks fetched ahead (App.svelte). V8 compiles a function only on its first call,
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

export default defineConfig({
  // relative URLs: the same build works at kbtu.sow.kz/ and under a sub-path like /next/
  base: './',
  plugins: [svelte(), preloads(), compileHints(/^(EventSheet|PersonSheet|ClubSheet)$/)],
  server: { host: true, port: 5180 },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // iOS 15 still runs Telegram; syntax is lowered for it, the app stays modern otherwise
    target: ['es2020', 'safari15', 'chrome100'],
    assetsInlineLimit: 0,
  },
});
