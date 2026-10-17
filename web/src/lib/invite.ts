// The club's invite (§4.5): a fresh one-time link per share (one person, 48 h), so a page view makes none; sent as our
// bot's card in the chat (a line and a button, no bare link: owner, Oct 4), the plain link only on old Telegram.
// Team's header and Studio's actions both share it.
import { api } from './api';
import { t } from './i18n/index.svelte';
import { say } from './state/ui.svelte';
import { shareCard } from './tg';

export async function shareInvite(org: { id: number; name: string }) {
  try {
    const link = `https://t.me/KBTUappBot?startapp=join_${org.id}_${(await api.invite(org.id)).token}`;
    await shareCard({ kind: 'join', id: String(org.id) }, link, t('team.inviteMsg', { club: org.name }));
  } catch { say(t('common.error'), 'pleading_face_3d'); }
}
