import { expect, test } from 'vitest';
import { linkDraft, linkUrl, linked, videoLinks } from './social';

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

test('links inside a post text: with or without https, a trailing dot left as text; the networks as buttons', () => {
  expect(linked('Our TikTok: tiktok.com/@kbtu/video/1. And https://kbtu.kz!')).toEqual([
    { s: 'Our TikTok: ' }, { s: 'tiktok.com/@kbtu/video/1', url: 'https://tiktok.com/@kbtu/video/1' }, { s: '. And ' },
    { s: 'https://kbtu.kz', url: 'https://kbtu.kz' }, { s: '!' }]);
  expect(linked('no links here')).toEqual([{ s: 'no links here' }]);
  expect(videoLinks('t.me/kbtu https://www.instagram.com/p/x https://youtu.be/y https://instagram.com/p/x https://tiktok.com/@a')
    .map((x) => x.kind)).toEqual(['instagram', 'youtube']);
});
