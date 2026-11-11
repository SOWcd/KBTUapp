import { expect, test } from 'vitest';
import { classEmoji, lessonKind } from './subjects';

const c = (subject: string, names: Record<string, string> | null = null, kind: string | null = null) => ({ subject, names, kind });

test('a class gets its icon from its names in any language', () => {
  // the owner's
  expect(classEmoji(c('Физическая культура', { en: 'Physical culture', kk: 'Дене шынықтыру' }))).toBe('soccer_ball_3d');
  expect(classEmoji(c('General Kazakh language'))).toBe('speech_balloon_3d');
  expect(classEmoji(c('Архитектура компьютера', { en: 'Computer architecture' }))).toBe('desktop_computer_3d');
  expect(classEmoji(c('Базы данных', { en: 'Databases' }))).toBe('file_cabinet_3d');
  // the order: physical culture isn't physics, networks aren't computers, history isn't a language
  expect(classEmoji(c('Физика'))).toBe('atom_symbol_3d');
  expect(classEmoji(c('Компьютерные сети'))).toBe('globe_with_meridians_3d');
  expect(classEmoji(c('История Казахстана'))).toBe('scroll_3d');
  expect(classEmoji(c('Machine learning'))).toBe('robot_3d');
  expect(classEmoji(c('Algorithms and data structures'))).toBe('laptop_3d');
  expect(classEmoji(c('Calculus 1'))).toBe('triangular_ruler_3d');
  expect(classEmoji(c('Probability and statistics'))).toBe('game_die_3d');
  expect(classEmoji(c('Transport logistics'))).toBe('books_3d');                 // no "sport" inside "transport"
  expect(classEmoji(c('Unknown subject', null, 'Лабораторная'))).toBe('microscope_3d');
  expect(classEmoji(c('Unknown subject', null, 'Лекция'))).toBe('books_3d');
});

test('lesson kind in three languages', () => {
  expect(['Лекция', 'Практика', 'Лабораторная', 'Дәріс', 'Practice', 'Lecture', null].map(lessonKind))
    .toEqual(['lecture', 'practice', 'lab', 'lecture', 'practice', 'lecture', null]);
});
