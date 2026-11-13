// The announcement fill (server logic/assistant.py `filled`): which of the editor's rows the AI filled, to mark them
// until the organiser touches one, and which of date, time and place it couldn't find, the short list at the top.
export type Filled = { title?: string; date?: string; start?: string; end?: string; place?: string; description?: string; price?: number };
export type Marked = 'title' | 'when' | 'place' | 'about' | 'price';

export function marked(x: Filled, canPrice: boolean): Marked[] {
  return [
    ...(x.title ? ['title' as const] : []),
    ...(x.date || x.start || x.end ? ['when' as const] : []),
    ...(x.place ? ['place' as const] : []),
    ...(x.description ? ['about' as const] : []),
    ...(x.price && canPrice ? ['price' as const] : []),
  ];
}

/** what the form still lacks of the three a fill most often misses (the place is fine as "to be announced") */
export function missing(f: { date: string; start: string; place: string; tba: boolean }): ('date' | 'time' | 'place')[] {
  return [...(f.date ? [] : ['date' as const]), ...(f.start ? [] : ['time' as const]), ...(f.place.trim() || f.tba ? [] : ['place' as const])];
}

/** the form's fields "Add more" works on, as typed (price: '' when free) */
export type FillForm = { title: string; date: string; start: string; end: string; place: string; description: string; price: string };
export type Differs = 'date' | 'start' | 'end' | 'place' | 'price';

/** "Add more" (owner, Nov 13): a second message into a form already filled. What the form has is never overwritten, an
 *  empty field takes the new value (a field still at its default, `dflt`, counts as empty), the description is the
 *  model's merge of both; a filled field the new text says otherwise is only listed, for a tap to accept. */
export function merge(now: FillForm, x: Filled, dflt: Partial<FillForm> = {}): { set: Partial<FillForm>; differs: { k: Differs; v: string }[] } {
  const set: Partial<FillForm> = {}, differs: { k: Differs; v: string }[] = [];
  const empty = (k: keyof FillForm) => !now[k].trim() || now[k] === dflt[k];
  if (x.title && empty('title')) set.title = x.title;
  if (x.description) set.description = x.description;
  const got: [Differs, string | undefined][] = [['date', x.date], ['start', x.start], ['end', x.end], ['place', x.place], ['price', x.price ? String(x.price) : undefined]];
  for (const [k, v] of got) {
    if (!v) continue;
    if (empty(k)) set[k] = v;
    else if (v.trim() !== now[k].trim()) differs.push({ k, v });
  }
  return { set, differs };
}
