// KBTU's anthem, its words as written (content: the same in every UI language). Trilingual by design: verse 1 in
// Kazakh, verse 2 in English, verse 3 in Russian, the Kazakh chorus after each. '' between two lines: a new stanza.
import type { Lang } from './index.svelte';

/** t: where the line starts in the recording, in seconds (null until timed); end: where it stops, marked only when a
 *  pause follows it; i: its place among the sung lines */
export type AnthemLine = { text: string; t: number | null; end: number | null; i: number };
export type AnthemPart = { kind: 'verse' | 'chorus'; lang: Lang; n?: number; lines: AnthemLine[] };

const CHORUS = [
  'ҚБТУ – киелі орда, білім мекен,',
  'Болашаққа бастайды сенімменен.',
  'Инновация – қанат, ой – еркіндік,',
  'Самғаймыз біз әлемге өр рухпенен!',
];

const PARTS: (Omit<AnthemPart, 'lines'> & { lines: string[] })[] = [
  { kind: 'verse', lang: 'kk', n: 1, lines: [
    'Тың ойдың қайнары,',
    'ҚБТУ - жастықтың айбары!',
    'Бабалар дәстүрін жалғаймыз,',
    'Биікке көтеріп байрағын!',
    '',
    'ҚБТУ – Бақыттың ордасы!',
    'Жалынды жастардың ортасы.',
    'Мақтаным, мәртебем өзіңсің,',
    'Арман мен Сенімнің жол басы!',
  ] },
  { kind: 'chorus', lang: 'kk', lines: CHORUS },
  { kind: 'verse', lang: 'en', n: 2, lines: [
    'KBTU – where bright ideas start,',
    'The pride and spirit of the young at heart.',
    'We keep our ancestors’ legacy alive',
    'And raise our banner high with pride.',
    '',
    'KBTU – a place of hope and light,',
    'Where driven youth reach shining heights.',
    'You are our honor, dream, and way,',
    'Leading us toward a brighter day.',
  ] },
  { kind: 'chorus', lang: 'kk', lines: CHORUS },
  { kind: 'verse', lang: 'ru', n: 3, lines: [
    'КБТУ – опора молодых,',
    'Источник замыслов больших.',
    'Заветы предков бережно храним',
    'И к новым достижениям спешим.',
    '',
    'КБТУ – ты гордость, статус и успех,',
    'Познаний счастья, радости для всех.',
    'Ты даришь силы нам идти',
    'И верный путь к мечте найти.',
  ] },
  { kind: 'chorus', lang: 'kk', lines: CHORUS },
];

// Each sung line's start in the recording (s), in the order sung: verse 1 (8 lines), the chorus (4), verse 2 (8), the
// chorus (4), verse 3 (8), the chorus (4), 36 in all; [start, end] for a line with its end marked (a pause after it).
// The creator taps and fixes them in the anthem sheet's editor (its timer) and the copied list goes here; until all 36
// are in, the words don't follow the song. Oct 30: his first pass, slips and all (chorus 1 has a double tap, chorus 2
// a missed line, so verse 3 on runs a line late): the editor is how he fixes them.
export const TIMES: (number | [number, number])[] = [20.18, 24.4, 28.36, 32.19, 35.79, 39.58, 43.59, 47.76, 53.37, 57.14, 64.84, 65.62,
  83.42, 87.24, 91.19, 95.77, 98.38, 102.27, 106.29, 112.11, 116.09, 119.65, 123.76, 142.48,
  146.43, 150.25, 153.83, 157.54, 161.8, 165.58, 171.07, 177.34, 182.87, 186.45, 190.62, 196.87];

let k = 0;
const at = (x: number | [number, number] | undefined) => (x == null ? { t: null, end: null } : Array.isArray(x) ? { t: x[0], end: x[1] } : { t: x, end: null });
export const ANTHEM: AnthemPart[] = PARTS.map((p) => ({ ...p, lines: p.lines.map((text) => (text ? { text, ...at(TIMES[k]), i: k++ } : { text, t: null, end: null, i: -1 })) }));
/** the sung lines in order (a chorus once for each time it is sung): what the timer stamps and the highlight follows */
export const SUNG = ANTHEM.flatMap((p) => p.lines.filter((l) => l.i >= 0));
export const TIMED = SUNG.every((l) => l.t != null);
