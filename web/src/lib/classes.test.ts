import { expect, test } from 'vitest';
import { classesLeft, classesOn, joinClasses } from './classes';
import { at, dayNo } from './time';

const c = (weekday: number, begins: string, ends: string, subject = 'Algorithms', room: string | null = '388') =>
  ({ weekday, begins, ends, subject, kind: null, room, teacher: null });

test('back-to-back classes of one subject in one room are one class', () => {
  expect(joinClasses([c(3, '13:00', '14:00'), c(3, '12:00', '13:00'), c(3, '14:00', '15:00', 'Kazakh', '251')]))
    .toEqual([c(3, '12:00', '14:00'), c(3, '14:00', '15:00', 'Kazakh', '251')]);                     // the owner's Wednesday
  expect(joinClasses([c(1, '12:00', '12:50'), c(1, '13:00', '13:50'), c(1, '14:00', '14:50')])).toEqual([c(1, '12:00', '14:50')]);
  expect(joinClasses([c(1, '12:00', '13:00'), c(1, '13:00', '14:00', 'Algorithms', '376')])).toHaveLength(2); // another room
  expect(joinClasses([c(1, '12:00', '13:00'), c(1, '13:30', '14:30')])).toHaveLength(2);                      // a long break
  expect(joinClasses([c(1, '12:00', '13:00'), c(2, '13:00', '14:00')])).toHaveLength(2);                      // another day
});

test("a day's classes with their times, and what's left of today", () => {
  const wed = at(2026, 9, 21, 12, 30);                                   // Wed, Oct 21 2026, 12:30 in Almaty
  const week = [c(3, '14:00', '15:00', 'Kazakh', '251'), c(3, '12:00', '13:00'), c(3, '09:00', '10:00', 'Physics'), c(4, '09:00', '10:00')];
  expect(classesOn(week, dayNo(wed)).map((x) => x.c.subject)).toEqual(['Physics', 'Algorithms', 'Kazakh']);
  expect(classesOn(week, dayNo(wed))[1].b).toBe(at(2026, 9, 21, 12, 0));
  expect(classesLeft(week, wed).map((x) => x.c.subject)).toEqual(['Algorithms', 'Kazakh']); // the one on now first
});
