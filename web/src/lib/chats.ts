// The chats directory (SPEC §4.11): opening a chat goes through Telegram; a student's first open ticks it on the server.
import { api, type Chat } from './api';
import { session } from './state/session.svelte';
import { i18n } from './i18n/index.svelte';
import { openLink, haptic } from './tg';

export async function openChat(c: Chat): Promise<void> {
  haptic.tap();
  openLink(c.url);
  if (session.me?.student && !c.opened) await api.chatOpened(c.id).catch(() => {});
}

/** "Suggest a chat" (PLAN item 45): the bot's own Telegram chat picker, one tap per chat; the admins check it. */
export function suggestChat(): void {
  haptic.tap();
  openLink('https://t.me/KBTUappBot?start=chat');
}

/** 8400 → "8.4K", in the app's language (Russian and Kazakh write it their way). */
export const compact = (n: number): string => new Intl.NumberFormat(i18n.lang === 'kk' ? 'kk-KZ' : i18n.lang === 'en' ? 'en-US' : 'ru-RU', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
