// The assistant's conversation (screens/assistant): kept while the app is open, so closing the sheet and coming back
// finds it; never stored (the server keeps no questions either).
import type { AssistReply, Id } from '../api';
// an answer keeps its question (to send on 👎), the vote given and whether it was sent
export type Turn = { role: 'user' | 'assistant'; text: string } & Partial<Omit<AssistReply, 'text'>> & { q?: string; vote?: 'up' | 'down'; sent?: boolean; err?: boolean /* a failed call that may be tried again */ };
/** the card "Ask AI" was tapped on: its id goes with each question (the server reads its facts), the title is only shown */
export type AskCtx = { kind: 'event' | 'club'; id: Id; title: string };
export const chat = $state<{ turns: Turn[]; ctx: AskCtx | null }>({ turns: [], ctx: null });
/** opening the assistant from this card (or none) starts a new conversation: none yet, or another card's */
export const fresh = (ctx?: AskCtx): boolean => !chat.turns.length || chat.ctx?.kind !== ctx?.kind || chat.ctx?.id !== ctx?.id;

// ponytail: a temporary switch while the owner picks the assistant's look: `&kri=a` or `&kri=b` at the end of the launch
// link; none: the look as it was. Goes, with the two looks not picked, once he has chosen.
export const LOOK = ((typeof location !== 'undefined' && /[#&]kri=([ab])/.exec(location.hash)?.[1]) || '') as '' | 'a' | 'b';
