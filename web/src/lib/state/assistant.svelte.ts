// The assistant's conversation (screens/assistant): kept while the app is open, so closing the sheet and coming back
// finds it; never stored (the server keeps no questions either).
import type { AssistReply, Id } from '../api';
// an answer keeps its question (to send on 👎), the vote given and whether it was sent
export type Turn = { role: 'user' | 'assistant'; text: string } & Partial<Omit<AssistReply, 'text'>> & { q?: string; vote?: 'up' | 'down'; sent?: boolean; err?: boolean /* a failed call that may be tried again */ };
/** the card "Ask AI" was tapped on: its id goes with each question (the server reads its facts), the title is only shown */
export type AskCtx = { kind: 'event' | 'club'; id: Id; title: string };
type Conversation = { turns: Turn[]; ctx: AskCtx | null; busy: boolean };
const chat = $state<{ current: Conversation }>({ current: { turns: [], ctx: null, busy: false } });
/** opening the assistant from this card (or none) starts a new conversation: none yet, or another card's */
export const fresh = (ctx?: AskCtx): boolean => !chat.current.turns.length || chat.current.ctx?.kind !== ctx?.kind || chat.current.ctx?.id !== ctx?.id;

/** A mounted sheet keeps its own conversation while another one is above it. */
export function conversation(ctx?: AskCtx): Conversation {
  if (fresh(ctx)) chat.current = { turns: [], ctx: ctx ?? null, busy: false };
  return chat.current;
}

export function rememberConversation(current: Conversation): void {
  chat.current = current;
}
