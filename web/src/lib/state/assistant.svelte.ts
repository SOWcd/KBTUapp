// The assistant's conversation (screens/assistant): kept while the app is open, so closing the sheet and coming back
// finds it; never stored (the server keeps no questions either).
export type Turn = { role: 'user' | 'assistant'; text: string; actions?: ({ type: 'map'; room: string } | { type: 'event'; id: number })[] };
export const chat = $state<{ turns: Turn[] }>({ turns: [] });
