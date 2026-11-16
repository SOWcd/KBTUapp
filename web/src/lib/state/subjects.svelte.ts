// The subjects' cards (screens/subjects): the whole list (~500 names, one read with everyone's counts), asked for with
// the app once it's idle (App) so the Forum tab's row and my timetable's classes open their card in the tap's frame;
// each card's people asked for as the finger lands (prefetch), kept half a minute. In memory only.
import { api, type Subject, type SubjectCard, type Subjects } from '../api';
import { byName } from '../subjects';
import { CONSENT_VOL } from '../legal';
import { session } from './session.svelte';

/** The cards are mine to read without asking: on (the server's file) and I agreed to the policy in force. Loads the app
 *  makes by itself (idle, the week) wait for it: an earlier policy is asked in place, when I open the list myself. */
export function subjReady(): boolean {
  const s = session.me?.student;
  return !!session.me?.subjects && !!s && ['staff', 'admin', session.policy, session.policy + CONSENT_VOL].includes(s.consent);
}

export const subj = $state({ all: null as Subjects | null });
let idxOf: Subject[] | null = null, idx = new Map<string, Subject>();
/** The cards by folded name (a timetable's class finds its own), built again only when the list is new. */
export function subjIndex(): Map<string, Subject> {
  const l = subj.all?.subjects ?? null;
  if (l !== idxOf) { idxOf = l; idx = byName(l ?? []); }
  return idx;
}

let asked: Promise<void> | null = null;
export function loadSubjects(fresh = false): Promise<void> {
  if (asked && !fresh) return asked;
  return (asked = api.subjects().then((s) => { subj.all = s; }, () => { asked = null; }));
}

const cards = new Map<string, { at: number; p: Promise<SubjectCard> }>();
const FRESH = 30_000; // a card's people asked again after this (a prefetch on the finger and the open share one read)
export function subjectCard(id: string): Promise<SubjectCard> {
  const k = cards.get(id);
  if (k && Date.now() - k.at < FRESH) return k.p;
  const p = api.subject(id);
  cards.set(id, { at: Date.now(), p });
  p.catch(() => cards.delete(id));
  return p;
}
export const keepCard = (c: SubjectCard): void => { cards.set(c.id, { at: Date.now(), p: Promise.resolve(c) }); };
