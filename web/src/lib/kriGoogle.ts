// The assistant's own yes to Google's Gemini answering first (server assistant.GOOGLE_YES; the policy names Google, but
// those who agreed before it did never said yes to it, and nobody is asked to accept the policy again). Asked by one
// quiet card on the assistant's empty opening, given or taken back in Settings → Privacy. me.kriGoogle absent: Google
// isn't open to me (no key, ASSIST_LEAD=off, an earlier policy), so neither the card nor the row shows.
import { api } from './api';
import { session } from './state/session.svelte';
import { say } from './state/ui.svelte';
import { t } from './i18n/index.svelte';
import { haptic } from './tg';

const LATER = 30 * 86400e3; // "Not now": the card rests this long on this phone (not a "no": nothing is sent)
const key = () => `kri.g.later.${session.me?.id}`;

/** "Not now" was tapped in the last 30 days here; storage blocked: as if it was (never nag) */
export function resting(): boolean {
  try { return Date.now() - Number(localStorage.getItem(key()) || 0) < LATER; } catch { return true; }
}

export function rest(): void {
  try { localStorage.setItem(key(), String(Date.now())); } catch { /* blocked: this opening only */ }
}

/** the yes given (on) or taken back: at once, back if the server says no */
export async function setKriGoogle(on: boolean): Promise<boolean> {
  const me = session.me;
  if (me?.kriGoogle == null) return false;
  if (me.kriGoogle === on) return true;
  me.kriGoogle = on;
  try { me.kriGoogle = (await api.kriGoogle(on)).yes; haptic.ok(); return me.kriGoogle === on; }
  catch { me.kriGoogle = !on; haptic.error(); say(t('common.error'), 'warning_3d'); return false; }
}
