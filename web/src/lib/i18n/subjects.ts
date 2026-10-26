// A class's icon in the capsule: a Fluent 3D emoji picked by words in the
// subject's names in all three languages (the schedule's `names`, else `subject`); the first match wins, so the more
// specific come first (physical culture before physics, networks before computers, history before languages).
// No "sport": it hides in "transport". A lab with no match gets the microscope, anything else books. Lives under
// i18n: the words are Russian and Kazakh too.
import type { ClassItem } from '../api';

const ICONS: [string, string[]][] = [
  ['soccer_ball_3d', ['physical culture', 'physical education', 'физическ', 'физкульт', 'дене шынықтыру']],
  ['robot_3d', ['artificial intelligence', 'machine learning', 'deep learning', 'neural', 'искусствен', 'машинн', 'нейрон', 'жасанды интеллект']],
  ['locked_3d', ['security', 'cryptograph', 'безопасност', 'криптограф', 'қауіпсіздік']],
  ['file_cabinet_3d', ['database', 'data base', 'баз данн', 'базы данн', 'дерекқор', 'sql']],
  ['globe_with_meridians_3d', ['network', 'internet', 'сети', 'сетев', 'интернет', 'желі']],
  ['desktop_computer_3d', ['computer architecture', 'operating system', 'computer organization', 'архитектур', 'операционн', 'компьютер']],
  ['game_die_3d', ['statistic', 'probabilit', 'статистик', 'вероятност', 'ықтималдық']],
  ['triangular_ruler_3d', ['math', 'calculus', 'algebra', 'geometr', 'discrete', 'математ', 'алгебр', 'геометр', 'дискрет']],
  ['atom_symbol_3d', ['physics', 'физик']],
  ['test_tube_3d', ['chemistr', 'хими']],
  ['laptop_3d', ['programming', 'algorithm', 'software', 'coding', 'python', 'java', 'web', 'information', 'программ', 'алгоритм', 'бағдарлама', 'информац', 'ақпарат']],
  ['dna_3d', ['biolog', 'genetic', 'биолог', 'генет']],
  ['oil_drum_3d', ['oil', 'gas', 'petroleum', 'geolog', 'drilling', 'нефт', 'газ', 'геолог', 'бурен', 'мұнай']],
  ['high_voltage_3d', ['energ', 'electric', 'power', 'энерг', 'электр']],
  ['chart_increasing_3d', ['econom', 'financ', 'accounting', 'marketing', 'эконом', 'финанс', 'бухгалт', 'маркетинг', 'қаржы']],
  ['briefcase_3d', ['manage', 'business', 'entrepreneur', 'менеджмент', 'управлен', 'бизнес', 'предприним', 'басқару']],
  ['balance_scale_3d', ['law', 'legal', 'право', 'правов', 'юрид', 'құқық']],
  ['brain_3d', ['psycholog', 'психолог']],
  ['scroll_3d', ['history', 'истори', 'тарих']],
  ['thinking_face_3d', ['philosoph', 'философ']],
  ['speech_balloon_3d', ['language', 'english', 'kazakh', 'russian', 'turkish', 'chinese', 'german', 'french', 'язык', 'английск', 'казахск', 'русск', 'тіл']],
  ['artist_palette_3d', ['design', 'drawing', 'graphic', 'дизайн', 'графи', 'черчен', 'сызу']],
];

export function classEmoji(c: Pick<ClassItem, 'subject' | 'kind' | 'names'>): string {
  const text = [c.subject, ...Object.values(c.names ?? {})].join(' | ').toLowerCase();
  const hit = ICONS.find(([, words]) => words.some((w) => text.includes(w)));
  if (hit) return hit[0];
  return /lab|лаб|зертхана/i.test(c.kind ?? '') ? 'microscope_3d' : 'books_3d';
}

// A class's short name in the List (one row per class, the long names were cut off): the long phrases
// a KBTU subject is made of, shortened when one is the whole name, so "Физическая культура 2" reads "Физ-ра 2" and a tail in
// brackets stays. The full name is a tap away (the "I won't go" question names it). Common short forms only.
const SHORT: [RegExp, string][] = [
  [/физическая культура/i, 'Физ-ра'], [/physical (culture|education)/i, 'PE'],
  [/(общий )?казахский язык/i, 'Казахский'], [/(general )?kazakh language/i, 'Kazakh'], [/жалпы қазақ тілі/i, 'Қазақ тілі'],
  [/русский язык/i, 'Русский'], [/russian language/i, 'Russian'],
  [/(профессионально-ориентированный )?иностранный язык/i, 'Ин. язык'], [/английский язык/i, 'Английский'],
  [/(professionally[- ]oriented )?foreign language/i, 'Foreign lang.'], [/english language/i, 'English'],
  [/архитектура (компьютера|эвм)/i, 'Архитектура ЭВМ'], [/computer architecture/i, 'Comp. architecture'], [/компьютер архитектурасы/i, 'Комп. архитектура'],
  [/объектно-ориентированное программирование/i, 'ООП'], [/object[- ]oriented programming/i, 'OOP'],
  [/алгоритмы и структуры данных/i, 'АиСД'], [/algorithms and data structures/i, 'ADS'],
  [/информационно-коммуникационные технологии/i, 'ИКТ'], [/information and communication technolog(y|ies)/i, 'ICT'],
  [/ақпараттық-коммуникациялық технологиялар/i, 'АКТ'],
  [/современная история казахстана/i, 'История Казахстана'], [/modern history of kazakhstan/i, 'History of Kazakhstan'],
  [/қазақстанның қазіргі заман тарихы/i, 'Қазақстан тарихы'],
  [/модуль социально-политических знаний/i, 'МСПЗ'], [/module of socio-political knowledge/i, 'MSPK'],
  [/математический анализ/i, 'Матанализ'],
  [/теория вероятностей и математическая статистика/i, 'Теорвер и матстат'], [/probability (theory )?and (mathematical )?statistics/i, 'Probability & stats'],
];

// only when the phrase is the whole name but a number or a bracket after it: "Kazakh language and literature" stays whole
const TAIL = String.raw`(?=\s*(?:\d+|[IVX]+|\(.*\))?\s*$)`;
const RULES = SHORT.map(([re, short]) => [new RegExp(`^(?:${re.source})${TAIL}`, 'i'), short] as const);
export const shortSubject = (name: string): string => {
  const s = name.trim();
  const hit = RULES.find(([re]) => re.test(s));
  return hit ? s.replace(hit[0], hit[1]) : s;
};

/** Lecture, lab or practice from the portal's lessonType, which comes in the student's language (*  "a lecture or a practice" at a glance); null when the portal says nothing we know. */
export function lessonKind(kind: string | null): 'lecture' | 'lab' | 'practice' | null {
  if (!kind) return null;
  if (/лек|lect|дәріс|дарис/i.test(kind)) return 'lecture';
  if (/лаб|lab|зертх/i.test(kind)) return 'lab';
  return /пр|prac|тәж|сем/i.test(kind) ? 'practice' : null;
}
