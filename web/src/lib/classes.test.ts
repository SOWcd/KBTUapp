import { expect, test } from 'vitest';
import { joinClasses } from './classes';

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
