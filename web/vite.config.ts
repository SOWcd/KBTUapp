import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  // relative URLs: the same build works at kbtu.sow.kz/ and under a sub-path like /next/
  base: './',
  plugins: [svelte()],
  server: { host: true, port: 5180 },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // iOS 15 still runs Telegram; syntax is lowered for it, the app stays modern otherwise
    target: ['es2020', 'safari15', 'chrome100'],
    assetsInlineLimit: 0,
  },
});
