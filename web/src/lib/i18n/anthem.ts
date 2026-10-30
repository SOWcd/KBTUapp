// KBTU's anthem, its words as written (content: the same in every UI language). Trilingual by design: verse 1 in
// Kazakh, verse 2 in English, verse 3 in Russian, the Kazakh chorus after each. '' between two lines: a new stanza.
import type { Lang } from './index.svelte';

/** t: where the line starts in the recording, in seconds (null until timed); i: its place among the sung lines */
export type AnthemLine = { text: string; t: number | null; i: number };
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
// chorus (4), verse 3 (8), the chorus (4), 36 in all. The creator taps them in the anthem sheet (its timer) and the
// copied list goes here; until all 36 are in, the words don't follow the song.
const TIMES: number[] = [];

let k = 0;
export const ANTHEM: AnthemPart[] = PARTS.map((p) => ({ ...p, lines: p.lines.map((text) => (text ? { text, t: TIMES[k] ?? null, i: k++ } : { text, t: null, i: -1 })) }));
/** the sung lines in order (a chorus once for each time it is sung): what the timer stamps and the highlight follows */
export const SUNG = ANTHEM.flatMap((p) => p.lines.filter((l) => l.i >= 0));
export const TIMED = SUNG.every((l) => l.t != null);
