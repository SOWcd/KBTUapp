import { describe, expect, it } from 'vitest';
import { richParts } from './richText';

describe('Telegram text ranges', () => {
  it('keeps bold inside one link after a UTF-16 surrogate pair and drops a non-HTTP target', () => {
    expect(richParts('🎤 Join us! More', [
      ['text_link', 3, 7, 'https://example.com/join'],
      ['bold', 8, 2],
      ['text_link', 12, 4, 'tg://resolve?domain=example'],
    ])).toEqual([
      '🎤 ',
      { mark: { kind: 'text_link', start: 3, end: 10, url: 'https://example.com/join' }, text: '', children: [
        'Join ',
        { mark: { kind: 'bold', start: 8, end: 10 }, text: '', children: ['us'] },
      ] },
      '! More',
    ]);
  });

  it('splits crossing styles and preserves both', () => {
    expect(richParts('abcd', [['bold', 0, 3], ['italic', 2, 2]])).toMatchObject([
      { mark: { kind: 'bold' }, children: ['ab', { mark: { kind: 'italic' }, children: ['c'] }] },
      { mark: { kind: 'italic' }, children: ['d'] },
    ]);
  });
});
