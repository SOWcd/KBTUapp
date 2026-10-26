// Friend invites (SPEC §4.7): my one-time link fr_<token>, the one the QR on the AddFriend sheet holds. It goes out as
// our bot's card — a line of text and a button, never a bare link in the chat; a plain t.me share only
// where Telegram is older than Bot API 8.0.
import { api } from './api';
import { shareCard } from './tg';
import { t } from './i18n/index.svelte';

export const friendUrl = (token: string): string => `https://t.me/KBTUappBot?startapp=fr_${token}`;

export async function shareFriendLink(): Promise<void> {
  const url = friendUrl((await api.friendLink()).token);
  await shareCard({ kind: 'fr' }, url, t('fr.shareText'));
}
