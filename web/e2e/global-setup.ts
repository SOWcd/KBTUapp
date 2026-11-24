// Telegram's own script (index.html loads it from telegram.org) once per run, served to every page from here: the
// pages don't wait on telegram.org, and a run still works offline with the copy from the last one.
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

export const TG_SCRIPT = resolve(import.meta.dirname, '.cache/telegram-web-app.js');

export default async function globalSetup(): Promise<void> {
  try {
    const r = await fetch('https://telegram.org/js/telegram-web-app.js?59');
    if (!r.ok) throw new Error(`telegram-web-app.js: ${r.status}`);
    mkdirSync(dirname(TG_SCRIPT), { recursive: true });
    writeFileSync(TG_SCRIPT, await r.text());
  } catch (e) {
    if (!existsSync(TG_SCRIPT)) throw e;
  }
}
