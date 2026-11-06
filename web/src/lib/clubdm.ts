// "Message the club" (Nov 6): a Telegram DM to its President (else the next by rank with a @username, the server's
// Org.contact) with a draft that names the club, and my own club when I'm in a team (collabs).
import type { Id, Membership } from './api/types';
import { t } from './i18n/index.svelte';
import { byRank } from './perms';

export function clubDm(contact: string, club: { id: Id; name: string }, mine: Membership[]): string {
  const from = [...mine].sort(byRank).find((m) => m.role !== 'member' && m.org.id !== club.id);
  const text = from ? t('join.dmFrom', { from: from.org.name, club: club.name }) : t('join.dm', { club: club.name });
  return `https://t.me/${contact}?text=${encodeURIComponent(text)}`;
}
