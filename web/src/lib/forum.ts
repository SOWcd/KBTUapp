// The student forum's topics (server logic/threads.py TOPICS): the four one picks and filters by, in this order, each
// with one line icon, monochrome (the selected chip alone takes the accent). Words: verbs bd.do.<topic> in the composer
// only, nouns bd.topic.<topic> on cards, filter chips and the moderators' list (a label must not read as a button), and
// bd.hint / bd.ph.<topic>. "vol" (People needed) is no longer offered: an old one shows as go, which it works like.
import type { Component } from 'svelte';
import CircleHelp from '@lucide/svelte/icons/circle-help';
import Gift from '@lucide/svelte/icons/gift';
import MapPin from '@lucide/svelte/icons/map-pin';
import MessageCircle from '@lucide/svelte/icons/message-circle';
import { api, ApiErr, type Thread, type Topic } from './api';
import { putThread } from './state/board.svelte';
import { say } from './state/ui.svelte';
import { t } from './i18n/index.svelte';
import { haptic } from './tg';

export const TOPICS = ['help', 'thing', 'go', 'talk'] as const;
export type Offered = (typeof TOPICS)[number];
/** what a thread's topic shows as, and its name on a card */
export const shown = (k: Topic): Offered => (k === 'vol' ? 'go' : k);
export const noun = (k: Topic): string => t(`bd.topic.${shown(k)}`);
export const TOPIC_ICON: Record<Offered, Component<any>> = { help: CircleHelp, thing: Gift, go: MapPin, talk: MessageCircle };
/** "I'm in" counts people on these */
export const gathers = (k: Topic): boolean => k === 'go' || k === 'vol';

/** A forum call failed: say why, in a toast. */
export function fail(e: unknown): void {
  haptic.error();
  const code = e instanceof ApiErr ? e.code : '';
  say(t(code === 'rate_limited' ? 'bd.slow' : code === 'not_found' ? 'bd.gone' : 'common.error'), 'pleading_face_3d');
}

/** "I'm in" on a gathering thread, or out again: on `th` at once, the server's answer settles it, the feed's card follows.
 *  `th` is state the caller owns (the feed's card, the thread's sheet). */
export async function join(th: Thread): Promise<void> {
  const on = !th.joined;
  th.joined = on; th.joins = Math.max(0, (th.joins ?? 0) + (on ? 1 : -1));
  haptic.select();
  try {
    const x = await api.joinThread(th.id, on);
    Object.assign(th, x); putThread(th.id, x);
    if (on) say(t('bd.inSay'), 'raising_hands_3d_default');
  } catch (e) { th.joined = !on; th.joins = Math.max(0, (th.joins ?? 0) + (on ? -1 : 1)); fail(e); }
}
