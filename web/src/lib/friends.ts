// My one invite link (owner, Nov 2): r_<link code>, the same for "Invite friends" and "Add a friend", in a QR or as our
// bot's card (a line and a button, never a bare link; a plain t.me share only where Telegram is older than Bot API
// 8.0). Opened, it lands on my card with "Add as a friend": one tap, friends; a newcomer counts as my referral.
import { shareCard } from './tg';
import { t } from './i18n/index.svelte';

export const inviteUrl = (code: string): string => `https://t.me/KBTUappBot?startapp=r_${code}`;

export const shareInvite = (code: string, ready?: () => void): Promise<boolean> => shareCard({ kind: 'rf', id: '0' }, inviteUrl(code), t('ref.text'), ready);
