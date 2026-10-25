// The club's invite (§4.5): a fresh one-time link per share (one person, 48 h), so a page view makes none; sent as our
// bot's card in the chat (a line and a button, no bare link; owner, Oct 4), the plain link only on old Telegram.
// Team's header and Studio's actions both share it.
import { api } from './api';
import { t } from './i18n/index.svelte';
import { say, ui } from './state/ui.svelte';
import { haptic, shareCard } from './tg';

export async function shareInvite(org: { id: number; name: string }, dept?: { id: number; name: string }) {
  if (ui.busy) return; // a second tap while the first link is made
  haptic.tap(); ui.busy = t('invite.making'); // the tap is felt and the capsule says so (nothing showed)
  try {
    const link = `https://t.me/KBTUappBot?startapp=join_${org.id}_${(await api.invite(org.id, dept?.id)).token}`;
    const msg = dept ? t('team.inviteDeptMsg', { club: org.name, dept: dept.name }) : t('team.inviteMsg', { club: org.name });
    await shareCard({ kind: 'join', id: String(org.id) }, link, msg, () => (ui.busy = ''));
  } catch { say(t('common.error'), 'pleading_face_3d'); }
  finally { ui.busy = ''; }
}
