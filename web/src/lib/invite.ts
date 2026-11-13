// The club's invite (§4.5): a fresh one-time link per share (one person, 48 h), so a page view makes none; or `many`, the
// team's one link for everyone (7 days, plain Members; the live one is shared again). Sent as our bot's card in the chat
// (a line and a button, no bare link), the plain link only on old Telegram. Team's header and Studio's actions share it.
import { api } from './api';
import { t } from './i18n/index.svelte';
import { say, ui } from './state/ui.svelte';
import { haptic, shareCard } from './tg';

/** made: the team's link exists (its end), told before the chat picker, which may never call back */
export async function shareInvite(org: { id: number; name: string }, dept?: { id: number; name: string }, many = false,
  made?: (expiresAt: number) => void): Promise<boolean> {
  if (ui.busy) return false; // a second tap while the first link is made
  haptic.tap(); ui.busy = t('invite.making'); // the tap is felt and the capsule says so (nothing showed)
  try {
    const r: { token: string; expiresAt?: number } = await (many ? api.teamLink(org.id) : api.invite(org.id, dept?.id));
    if (r.expiresAt) made?.(r.expiresAt);
    const link = `https://t.me/KBTUappBot?startapp=join_${org.id}_${r.token}`;
    const msg = many ? t('team.linkMsg', { club: org.name }) : dept ? t('team.inviteDeptMsg', { club: org.name, dept: dept.name }) : t('team.inviteMsg', { club: org.name });
    await shareCard({ kind: 'join', id: String(org.id), ...(many ? { many: true } : {}) }, link, msg, () => (ui.busy = ''));
    return true;
  } catch { say(t('common.error'), 'warning_3d'); return false; }
  finally { ui.busy = ''; }
}
