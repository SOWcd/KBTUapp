import type { EventInput, OwnTr, Question, MemoAsks } from './api/types';

// The announcement fill (server logic/assistant.py `filled`): which of the editor's rows the AI filled, to mark them
// until the organiser touches one, and which of date, time and place it couldn't find, the short list at the top.
export type Filled = { title?: string; date?: string; endDate?: string; start?: string; end?: string; place?: string; description?: string; price?: number };
/** Only facts the organizer has supplied. Zero means explicitly uncapped, false means explicitly declined. */
export type ChatFill = Filled & {
  emoji?: string; color?: string; tr?: OwnTr; online?: boolean; onlineUrl?: string; tba?: boolean; placeUrl?: string;
  paid?: boolean; payTo?: string; payPhone?: string; freeFirst?: number; seats?: number;
  registration?: 'start' | 'end' | 'date'; regDate?: string; regTime?: string;
  teams?: boolean; teamMin?: number; teamMax?: number; teamCap?: number;
  needsPhone?: boolean; santa?: boolean; volunteers?: number; volSenior?: boolean; form?: Question[];
  visibility?: EventInput['visibility']; leadersFrom?: EventInput['leadersFrom']; meeting?: boolean; forBoard?: boolean;
  schoolOnly?: boolean; cohost?: string; department?: string; memo?: MemoAsks;
  partner?: boolean; guestHost?: string; externalUrl?: string;
};

export function updateDraft(previous: ChatFill, patch: ChatFill): ChatFill {
  const d = { ...previous, ...patch };
  if (patch.paid === false) {
    delete d.price; delete d.payTo; delete d.payPhone; delete d.freeFirst;
  } else if (patch.price) d.paid = true;
  if (patch.teams === false) {
    delete d.teamMin; delete d.teamMax; delete d.teamCap;
  } else if (patch.teamMin || patch.teamMax || patch.teamCap !== undefined) d.teams = true;
  if (patch.onlineUrl || patch.online || patch.tba || patch.place) {
    d.online = !!(patch.onlineUrl || patch.online);
    d.tba = !d.online && !!patch.tba;
    if (d.online || d.tba) { delete d.place; delete d.placeUrl; }
    else if (patch.place && patch.place !== previous.place && !patch.placeUrl) delete d.placeUrl;
  }
  if (!d.online) delete d.onlineUrl;
  if (!patch.registration && (patch.regDate || patch.regTime)) d.registration = 'date';
  if (d.registration !== 'date') { delete d.regDate; delete d.regTime; }
  if (patch.visibility && patch.visibility !== 'members') { d.meeting = false; d.forBoard = false; delete d.department; }
  else if (patch.meeting || patch.forBoard || patch.department) d.visibility = 'members';
  if (patch.partner === false) { delete d.guestHost; delete d.externalUrl; }
  else if (patch.guestHost || patch.externalUrl) d.partner = true;
  if (patch.memo) {
    const memo = { ...previous.memo };
    for (const k of Object.keys(patch.memo) as (keyof MemoAsks)[]) Object.assign(memo, { [k]: { ...memo[k], ...patch.memo[k] } });
    d.memo = memo;
  }
  if (!patch.tr && (d.title !== previous.title || d.description !== previous.description)) delete d.tr;
  return d;
}

/** Ask only about applicable fields, including decisions the hand editor would otherwise default silently. */
export function nextQuestion(d: ChatFill, canPrice: boolean) {
  if (!d.title) return 'title';
  if (!d.date) return 'date';
  if (!d.start) return 'start';
  if (!d.place && !d.online && !d.tba) return 'place';
  const hasTickets = d.paid || d.seats || d.teams || d.registration && d.registration !== 'start' || d.santa || d.needsPhone || d.form?.length;
  if (d.meeting) return hasTickets || d.partner ? 'meeting' : 'ready';
  if (d.partner) {
    if (hasTickets || d.visibility && d.visibility !== 'public') return 'partner';
    if (!d.guestHost) return 'guestHost';
    if (!d.externalUrl) return 'externalUrl';
    return 'ready';
  }
  if (canPrice && d.paid === undefined) return 'paid';
  if (d.paid) {
    if (!canPrice) return 'paidRight';
    if (!d.price) return 'price';
    if (!d.payTo) return 'payTo';
    if (!d.payPhone) return 'payPhone';
  }
  if (d.seats === undefined) return 'seats';
  if (!d.registration || d.registration === 'end' && (d.paid || d.seats || d.teams || d.visibility && d.visibility !== 'public')) return 'registration';
  if (d.registration === 'date') {
    if (!d.regDate) return 'regDate';
    if (!d.regTime) return 'regTime';
  }
  if (d.teams === undefined) return 'teams';
  if (d.teams) {
    if (!d.teamMin) return 'teamMin';
    if (!d.teamMax || d.teamMax < d.teamMin) return 'teamMax';
    if (d.teamCap === undefined) return 'teamCap';
  }
  return 'ready';
}

export type Marked = 'title' | 'when' | 'place' | 'about' | 'price';

export function marked(x: Filled, canPrice: boolean): Marked[] {
  return [
    ...(x.title ? ['title' as const] : []),
    ...(x.date || x.endDate || x.start || x.end ? ['when' as const] : []),
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
export type FillForm = { title: string; date: string; endDate: string; start: string; end: string; place: string; description: string; price: string };
export type Differs = 'date' | 'start' | 'end' | 'place' | 'price';

/** "Add more": a second message into a form already filled. What the form has is never overwritten, an
 *  empty field takes the new value (a field still at its default, `dflt`, counts as empty), the description is the
 *  model's merge of both; a filled field the new text says otherwise is only listed, for a tap to accept. */
export function merge(now: FillForm, x: Filled, dflt: Partial<FillForm> = {}): { set: Partial<FillForm>; differs: { k: Differs; v: string }[] } {
  const set: Partial<FillForm> = {}, differs: { k: Differs; v: string }[] = [];
  const empty = (k: keyof FillForm) => !now[k].trim() || now[k] === dflt[k];
  if (x.title && empty('title')) set.title = x.title;
  if (x.description) set.description = x.description;
  if (x.endDate && empty('endDate')) set.endDate = x.endDate; // a later day only fills an empty one
  const got: [Differs, string | undefined][] = [['date', x.date], ['start', x.start], ['end', x.end], ['place', x.place], ['price', x.price ? String(x.price) : undefined]];
  for (const [k, v] of got) {
    if (!v) continue;
    if (empty(k)) set[k] = v;
    else if (v.trim() !== now[k].trim()) differs.push({ k, v });
  }
  return { set, differs };
}
