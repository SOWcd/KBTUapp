import { expect, test } from 'vitest';
import { clubDm } from './clubdm';
import type { Membership } from './api/types';

const m = (id: number, name: string, role: Membership['role']) => ({ org: { id, name }, role }) as unknown as Membership;

test('the draft names the club, and my top team club when I have one', () => {
  const plain = clubDm('prez', { id: 1, name: 'Chess' }, [m(2, 'Debate', 'member')]);
  expect(plain.startsWith('https://t.me/prez?text=')).toBe(true);
  const text = decodeURIComponent(plain.split('text=')[1]);
  expect(text).toContain('Chess');
  expect(text).not.toContain('Debate');
  const from = decodeURIComponent(clubDm('prez', { id: 1, name: 'Chess' }, [m(3, 'Art', 'head'), m(2, 'Debate', 'president'), m(1, 'Chess', 'president')]).split('text=')[1]);
  expect(from).toContain('Debate');
  expect(from).toContain('Chess');
  expect(from).not.toContain('Art');
});
