// The one copy-to-clipboard: a tick and a toast on success, the error buzz on failure (the caller adds its own word).
import { say } from '../lib/state/ui.svelte';
import { haptic } from '../lib/tg';

export async function copyText(text: string, ok: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); haptic.ok(); say(ok, 'sparkles_3d'); return true; }
  catch { haptic.error(); return false; }
}
