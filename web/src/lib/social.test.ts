import { expect, test } from 'vitest';
import { linkDraft, linkUrl } from './social';

test('a username becomes the network link; a pasted or bare address is kept; saved links come back as rows', () => {
  expect(linkUrl({ kind: 'instagram', v: '@kbtu.club' })).toBe('https://instagram.com/kbtu.club');
  expect(linkUrl({ kind: 'tiktok', v: 'kbtu' })).toBe('https://tiktok.com/@kbtu');
  expect(linkUrl({ kind: 'telegram', v: 'https://t.me/kbtu_it' })).toBe('https://t.me/kbtu_it');
  expect(linkUrl({ kind: 'web', v: 'kbtu.kz/clubs' })).toBe('https://kbtu.kz/clubs');
  expect(linkUrl({ kind: 'web', v: 'http://kbtu.kz' })).toBe('https://kbtu.kz');
  expect(linkUrl({ kind: 'web', v: 'not a link' })).toBeNull();
  expect(linkUrl({ kind: 'telegram', v: '' })).toBeNull();
  expect(linkDraft('https://www.instagram.com/kbtu.club/')).toEqual({ kind: 'instagram', v: 'kbtu.club' });
  expect(linkDraft('https://youtube.com/@kbtu')).toEqual({ kind: 'youtube', v: 'kbtu' });
  expect(linkDraft('https://youtube.com/channel/UC1')).toEqual({ kind: 'web', v: 'youtube.com/channel/UC1' });
  for (const u of ['https://t.me/kbtu_it', 'https://tiktok.com/@kbtu', 'https://kbtu.kz']) expect(linkUrl(linkDraft(u))).toBe(u);
});
