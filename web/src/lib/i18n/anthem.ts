// KBTU's anthem, its words as written (content: the same in every UI language). Trilingual by design: verse 1 in
// Kazakh, verse 2 in English, verse 3 in Russian, the Kazakh chorus after each. '' between two lines: a new stanza.
import type { Lang } from './index.svelte';

/** t: where the line starts in the recording, in seconds (null until timed); end: where it stops, marked only when a
 *  pause follows it; i: its place among the sung lines; w: its words; o: each word's start after the line's (s) */
export type AnthemLine = { text: string; t: number | null; end: number | null; i: number; w: string[]; o: number[] };
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
    'A place of hope and light,',
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
// Nov 2: forced alignment on the vocal stem (Demucs htdemucs; Meta's MMS aligner cross-checked with stable-ts/Whisper
// small, the two within 0.15 s on about 3 words in 4): a line starts at its first word. The owner's taps of Oct 30 ran a
// line late through the first two verses and choruses (the lit waiting line, see AnthemSheet); verse 3 and the last
// chorus within 0.5 s, the last chorus's first line 0.9 s early. The creator still fine-tunes them in his editor.
export const TIMES: (number | [number, number])[] = [
  16.63, 20.5, 24.34, 28.17, 31.93, 35.96, 39.58, 43.41,
  48.78, 53.33, 56.75, [60.71, 64.7],
  79.3, 83.11, 86.96, 90.74, 95.09, 98.29, 102.15, 105.94,
  111.66, 116.12, 119.64, [123.56, 129.7],
  142.13, 146.43, 149.74, 154.13, 157.85, 161.68, 165.5, 171.23,
  178.27, 182.78, 186.26, [190.24, 196.3],
];
// Each sung line's words after its first: when each starts, seconds after the line's start (the same alignment). Relative,
// so the creator's nudges of a line carry its words along.
const WORDS: number[][] = [
  [0.55, 1.49], [1.18, 2.46], [0.75, 2.3], [1.13, 2.39], [1.19, 2.43], [0.95, 2.24], [1.17, 2.4], [0.35, 1.12, 2.27, 3.76],
  [0.54, 1.36, 2.81, 3.32], [0.96, 1.91], [1.36, 2.55, 2.85], [0.7, 1, 1.95, 2.52],
  [1.49, 1.61, 1.95, 2.52], [0.16, 0.51, 0.65, 0.97, 1.45, 1.65, 2.09, 2.4], [0.12, 0.45, 0.74, 1.62, 1.92], [0.21, 0.47, 0.67, 1.6, 2.08, 2.32], [0.08, 0.39, 1.05, 1.47, 1.74], [0.2, 0.76, 1.07, 1.49, 2.46], [0.29, 0.57, 1.02, 1.67, 2.14, 2.36], [0.58, 0.93, 1.56, 1.68, 2.35],
  [0.49, 1.3, 2.8, 3.35], [1.01, 1.96], [1.31, 2.27, 2.74], [0.71, 1.01, 1.98, 2.55],
  [1.48, 2.64], [1.16, 2.33], [0.48, 1.67, 2.81], [0.08, 0.18, 0.61, 2.46], [0.99, 1.17, 2.17, 2.56, 2.89], [0.91, 1.92, 2.83, 2.98], [0.21, 1.07, 1.9, 2.47], [0.2, 0.89, 1.5, 1.65, 3.31],
  [0.56, 1.38, 2.91, 3.43], [1, 1.97], [1.38, 2.33, 2.86], [0.7, 0.98, 2.28, 2.55],
];

/** a line's words as sung: split at spaces, a dash going with the word before it ('ҚБТУ –') */
export const words = (text: string) => text.split(' ').reduce<string[]>((w, x) => (/[\p{L}\p{N}]/u.test(x) || !w.length ? w.push(x) : (w[w.length - 1] += ` ${x}`), w), []);

let k = 0;
const at = (x: number | [number, number] | undefined) => (x == null ? { t: null, end: null } : Array.isArray(x) ? { t: x[0], end: x[1] } : { t: x, end: null });
const line = (text: string) => ({ text, ...at(TIMES[k]), w: words(text), o: [0, ...(WORDS[k] ?? [])], i: k++ });
export const ANTHEM: AnthemPart[] = PARTS.map((p) => ({ ...p, lines: p.lines.map((text) => (text ? line(text) : { text, t: null, end: null, i: -1, w: [], o: [] })) }));
/** the sung lines in order (a chorus once for each time it is sung): what the timer stamps and the highlight follows */
export const SUNG = ANTHEM.flatMap((p) => p.lines.filter((l) => l.i >= 0));
export const TIMED = SUNG.every((l) => l.t != null);
