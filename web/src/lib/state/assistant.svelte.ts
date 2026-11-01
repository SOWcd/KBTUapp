// The assistant's conversation (screens/assistant): kept while the app is open, so closing the sheet and coming back
// finds it; never stored (the server keeps no questions either).
import type { AssistReply, Id } from '../api';
// an answer keeps its question (to send on 👎), the vote given and whether it was sent
export type Turn = { role: 'user' | 'assistant'; text: string } & Partial<Omit<AssistReply, 'text'>> & { q?: string; vote?: 'up' | 'down'; sent?: boolean };
/** the card "Ask AI" was tapped on: its id goes with each question (the server reads its facts), the title is only shown */
export type AskCtx = { kind: 'event' | 'club'; id: Id; title: string };
export const chat = $state<{ turns: Turn[]; ctx: AskCtx | null }>({ turns: [], ctx: null });
