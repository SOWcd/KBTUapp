// The chats directory (SPEC §4.11): opening a chat goes through Telegram; a student's first open ticks it on the server.
import { api, type Chat } from './api';
import { session } from './state/session.svelte';
import { sheets } from './state/sheets';
import { i18n } from './i18n/index.svelte';
import { openLink, haptic, tgTry } from './tg';

export async function openChat(c: Chat): Promise<void> {
  haptic.tap();
  openLink(c.url);
  if (session.me?.student && !c.opened) await api.chatOpened(c.id).catch(() => {});
}

/** "Suggest a chat" (PLAN item 45): the bot's own Telegram chat picker, one tap per chat; the admins check it. */
/** "Suggest a chat": the app's own sheet (the bot's chat left the screen empty); a guest signs in first. */
export function suggestChat(): void {
  haptic.tap();
  if (session.me?.student) sheets.suggestChat(); else sheets.login();
}
/** Telegram's own picker of my chats, in the bot (Mini Apps can't open it themselves). The bot's chat opens behind the
 *  app, so the app closes, as BotFather's buttons do. */
export const pickInTelegram = (): void => { haptic.tap(); openLink('https://t.me/KBTUappBot?start=chat'); setTimeout(() => tgTry((w) => w.close()), 300); };

/** 8400 → "8.4K", in the app's language (Russian and Kazakh write it their way). */
export const compact = (n: number): string => new Intl.NumberFormat(i18n.lang === 'kk' ? 'kk-KZ' : i18n.lang === 'en' ? 'en-US' : 'ru-RU', { notation: 'compact', maximumFractionDigits: 1 }).format(n);

/** The KBTU App's chats as one Telegram folder: Telegram offers to add it. A row on the app's own page. */
export const APP_FOLDER = 'https://t.me/addlist/VtFWmJ1lMboxZjli';

/** Studio's "Add our bot" to a club's chat (PLAN 86): a group by a start link that says which chat it is; a channel
 *  takes a bot only as an admin (the least: inviting, so Telegram tells the bot the chat's own link). */
export const addBotLink = (c: { id: number; kind: Chat['kind'] }): string =>
  c.kind === 'channel' ? 'https://t.me/KBTUappBot?startchannel&admin=invite_users' : `https://t.me/KBTUappBot?startgroup=oc_${c.id}`;
