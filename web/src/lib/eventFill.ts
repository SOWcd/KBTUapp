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
